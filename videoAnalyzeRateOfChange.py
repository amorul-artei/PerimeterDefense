#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      14.01.2022 voicua: Created "analyzeVideo.py" to test algorithms used in the analyzeVideo script.
#      19.01.2022 voicua: Renamed to "videoAnalyzeRateOfChange.py" to better reflect what this phase of the algorithm is doing
#      28.01.2022 voicua: Added parameter to enable highlighting the changes, to help with the tuning
#      17.02.2022 voicua: Major refactoring to allow for "defragmentation" of video sources by preserving analysis state between calls


import os
import sys
from time import perf_counter
import argparse

import imageio as iio
import ffmpeg
from PIL import Image
import numpy

import psutil
#import profile
#import gc

#from decord import VideoReader
#from decord import cpu, gpu
from vidgear.gears import CamGear


import videoAnalysisHelpers as vh

kLuminanceDiffThreshold = 32
kMotionDerivativeThreshold = 20.0 # percentage of change in modified pixel count
kMinChange = 1500
kTempFilePrefix = 'temp_ROC_'

redMask = None

#TODO-Pri2 voicua: consider moving helper functions in corresponding helper units
def FlagEnabled( args, flagName ):
    return (not args is None) and (flagName in args.__dict__) and args.__dict__[ flagName ]


def IsValueInInterval( point, thresholdAbsolute, valueToCheck ):
    return valueToCheck > point - thresholdAbsolute and valueToCheck < point + thresholdAbsolute

# threshold relative is given to this function as a fraction of the point
def IsValueInRelativeInterval( point, thresholdRelative, valueToCheck ):
    thresholdAbsolute = float( point ) * float( thresholdRelative )
    return IsValueInInterval( point, thresholdAbsolute, valueToCheck )


def PrepareFrameForAnalysis( frameRawData ):
    #TODO-Pri0 voicua: use aggregate (see python's "Panda") instead of Image to calculate Luminance
    #   currently PrepareFrameForAnalysis is the most expensive operation 
    img = Image.fromarray( frameRawData, 'RGB' )
    img = img.convert( 'L' )
    return numpy.array( img, numpy.int16 )


def MotionDerivativeDetected( previousCoefficient, newCoefficient ):
    if previousCoefficient < 0:
        return True

    if abs( newCoefficient - previousCoefficient ) < kMinChange:
        return False

    threshold = float( previousCoefficient * kMotionDerivativeThreshold / 100.0 )
    return (newCoefficient < previousCoefficient - threshold) or (newCoefficient > previousCoefficient + threshold)


def AlphaMaskCalculation( diff ):
    numpy.multiply( diff, 255, out = diff )
    numpy.minimum( diff, 255, out = diff )

    diff = numpy.reshape( diff, ( len( diff ), len( diff[ 0 ] ), 1 ) )
    diff = numpy.tile( diff, 3 )

    return diff


def CalculateDifferenceCoefficient( baseComparison, newComparison, currentFrame = None, args = None ):
    diff = (newComparison - baseComparison)
    numpy.divide( diff, kLuminanceDiffThreshold, out = diff, casting = 'unsafe' )

    diffCoefficient = numpy.count_nonzero( diff )

    if FlagEnabled( args, "highlightDiffs" ):

        # Use Alpha-Blending technique with alpha fully opaque to highlight the changed area.
        diff = AlphaMaskCalculation( diff )
        oneMinusDiff = numpy.subtract( 255, diff )

        #print( "Width = " + str( len( currentFrame ) ) + ", Height = " + str( len( currentFrame[ 0 ] ) ) )
        #print( "Channels = " + str( len( currentFrame[ 0 ][ 0 ] ) ) )
        #print( currentFrame.dtype )

        global redMask
        if redMask is None:
            colorRed = numpy.array( [ 255, 0, 0 ] )
            redMask = numpy.tile( colorRed, (len( currentFrame ), len( currentFrame[ 0 ] ), 1) )

        # do the alpha blending
        numpy.multiply( diff, redMask, out = diff )
        numpy.divide( diff, 255, out = diff, casting = 'unsafe' )

        if FlagEnabled( args, "onlyDiffs" ):
            numpy.multiply( currentFrame, 0, out = currentFrame )   # zero out the original image
        else:
            numpy.multiply( oneMinusDiff, currentFrame, out = oneMinusDiff )
            numpy.divide( oneMinusDiff, 255, out = currentFrame, casting = 'unsafe' )


        numpy.add( currentFrame, diff, out = currentFrame, casting = 'unsafe' )

    return diffCoefficient


# Looks like I am ending up duplicating the C++ constructs in Python, minus proper encapsulation
class RunningTimeAccumulator:
    def __init__( self ):
        self.accumulator = 0
        self.dataSize = 0.0
        self.lastTaskSize = 0.0
        self.lastTaskDuration = 0
        self.startTime = 0

    def OnStartTimer( self, dataSize = 0 ):
        self.startTime = perf_counter()
        self.dataSize += dataSize
        self.lastTaskSize = dataSize

    def OnStopTimer( self ):
        stopTime = perf_counter()
        self.lastTaskDuration = (stopTime - self.startTime)
        self.accumulator += self.lastTaskDuration

    def FormatAsMiBPerf( self, lastOnly = False ):
        if lastOnly:
            taskSize = self.lastTaskSize
            taskDuration = self.lastTaskDuration
        else:
            taskSize = self.dataSize
            taskDuration = self.accumulator
        if taskDuration == 0:
            return "? MiB/s"
        return "%.2f MiB/s" % ( taskSize / (1024.0 * 1024.0 * taskDuration ) )

class AlgorithmPerformanceResults:
    def __init__( self ):
        self.analysisAborted = False
        self.totalFramesInVideoFile = 0
            # Note: totalFramesInVideoFile approx totalFramesSkipped + totalFramesProcessed, unless there is a problem accessing all video frames
            # totalFramesInVideoFile is not calculated exactly, it's an approximation based on video duration.
        self.totalFramesProcessed = 0
        self.totalFramesSkipped = 0
        self.totalFramesTriggered = 0
        self.algorithmFPS = 0
        self.ResetPerfCounters()

    def ResetPerfCounters( self ):
        self.frameFetchingAccumulator = RunningTimeAccumulator()
        self.framePrepAccumulator = RunningTimeAccumulator()
        self.rocAnalysisAccumulator = RunningTimeAccumulator()


class ImageIOVideoIterator:
    def __init__( self, videoPathName ):
        self.videoReader = iio.get_reader( videoPathName )
        self.currentIndex = 0

    def ReadNextFrame( self ):
        nextFrame = self.videoReader.get_next_data()
        self.currentIndex += 1
        return nextFrame

    def SkipFrames( self, count ):
        self.videoReader.set_image_index( self.currentIndex + count )
            #no way to know how many were actually remaining in the stream
            #total frames calculations are approximate and for some streams unknown
        self.currentIndex += count

    def CurrentIndex( self ):
        return self.currentIndex

'''
class DecordVideoIterator:
    def __init__( self, videoPathName ):
        self.videoReader = VideoReader( videoPathName, ctx = cpu(0) )
        self.currentIndex = 0

    def ReadNextFrame( self ):
        gc.collect()
        nextFrame = self.videoReader.next().asnumpy()
        self.currentIndex += 1
        return nextFrame
        
    def SkipFrames( self, count ):
        self.videoReader.skip_frames( count )
        self.currentIndex += count

    def CurrentIndex( self ):
        return self.currentIndex
'''
'''
class VidGearVideoIterator:
    def __init__( self, videoPathName ):
        self.stream = CamGear( source = videoPathName ).start()
        self.currentIndex = 0

    def ReadNextFrame( self ):
        nextFrame = self.stream.read()
        self.currentIndex += 1
        return nextFrame

    def SkipFrames( self, count ):
        self.videoReader.set_image_index( self.currentIndex + count )
        self.currentIndex += count

    def CurrentIndex( self ):
        return self.currentIndex
'''

def CreateVideoIterator( videoPathName ):
    return ImageIOVideoIterator( videoPathName )


class RateOfChangeAnalyzer:
    def __init__( self, args, videoAnalysisName ):
        self.args = args
        self.videoAnalysisName = videoAnalysisName
        self.kRocTemporaryFilePath = os.path.join( args.destFolder, kTempFilePrefix + videoAnalysisName + ".mp4" )
        self.kRocAnalyzedFilePath = os.path.join( args.destFolder, videoAnalysisName + '_ROC_analyzed.mp4' )
        self.detectedFrames = []
        self.videoWriter = None
        self.totalFrameOutputCount = 0

        self.kWarmUpDuration = 2 * 60   # Amount of original video time before analysis can be aborted
        kMaxMemoryBuffer = 1000 # in MiB
        self.kMaxFramesToBuffer = int( (kMaxMemoryBuffer * 1024 * 1024) / (1920 * 1080 * 4) )

        # Accelerate processing of the video, by skipping frames if there are no triggers detected for some time
        # This is an optimization, to compensate for the really slow Python algorithms/image libraries.
        self.kNumLoopsUntriggeredThreshold = 100
        self.kMaxFrameSkip = 30
        self.frameSkip = 0

        self.baseFrame = None
        self.baseOfComparison = None
        self.baseDiffCoefficient = -1


    def AddVideoFileToAnalysis( self, videoPathName, logger, algPerformanceResults = None ):
        if algPerformanceResults is None:
            algPerformanceResults = AlgorithmPerformanceResults()

        # Figure out disk locations first
        if not os.path.isfile( videoPathName ):
            print( 'File not found: ' + videoPathName )
            return

        #tracemalloc.start()

        # Get video properties such as number of frames, duration, etc
        videoMeta = ffmpeg.probe( videoPathName )[ "streams" ]

        logger.PrintMessage( "Adding %s to frame rate-of-change analysis" % os.path.basename( videoPathName ) )
        logger.PrintMessage( 'Resolution: %ix%i' % (videoMeta[ 0 ][ 'width' ], videoMeta[ 0 ][ 'height' ]) )
        logger.PrintMessage( 'Average Frame Rate: ' + videoMeta[ 0 ][ 'avg_frame_rate' ] )
        logger.PrintMessage( 'Duration in seconds: ' + videoMeta[ 0 ][ 'duration' ] )

        frameRatePair = videoMeta[ 0 ][ 'avg_frame_rate' ].split( '/' )
        frameRate = float( frameRatePair[ 0 ] ) / float( frameRatePair[ 1 ] )
        kWarmUpFrameCount = frameRate * self.kWarmUpDuration

        totalFrames = int( frameRate * float( videoMeta[ 0 ][ 'duration' ] ) )
        logger.PrintMessage( 'Total frames: %i' % totalFrames )
        algPerformanceResults.totalFramesInVideoFile = totalFrames

        # Initialize video iterator
        videoIter = CreateVideoIterator( videoPathName )
        if self.baseFrame is None:
            self.baseFrame = videoIter.ReadNextFrame()
            self.baseOfComparison = PrepareFrameForAnalysis( self.baseFrame )
            self.baseDiffCoefficient = -1

        totalNumFramesTriggered = 0
        numLoopsUntriggered = 0 # currently, no triggering means there are no changes in the rate of changes

        # Time Compression statistics, used to abort analysis if the frames are changing all the time, in unpredictable ways
        timeCompressionRatio = 0.0
        prevTimeCompressionRatio = 0.0
        analysisAborted = False

        currentDetectedFrames = []  # Buffer to keep detected frames, in case they need to be discarded

        timerStart = perf_counter()
        frameIndexStarted = 0
        framesProcessedPerSecond = 0

        while not (self.baseOfComparison is None):

            #
            # Read the next frame. Skip some frames if we are in skipping mode (i.e. uninteresting portion of the video)
            #

            algPerformanceResults.frameFetchingAccumulator.OnStartTimer()

            currentFrame = None

            try:
                if self.frameSkip > 0 and videoIter.CurrentIndex() > 1 and \
                    videoIter.CurrentIndex() + self.frameSkip < totalFrames:

                    videoIter.SkipFrames( self.frameSkip )
                    algPerformanceResults.totalFramesSkipped += self.frameSkip

                currentFrame = videoIter.ReadNextFrame()

            except Exception as e:
                logger.PrintMessage( str( e ) )
                logger.PrintMessage( "Exception thrown by video decoder attempting to read frame index %i" % videoIter.CurrentIndex() )
                # TODO-Pri1 voicua: what if the file support media was unplugged?
                logger.PrintMessage( "Assuming end of file. Ending analysis." )

            algPerformanceResults.frameFetchingAccumulator.OnStopTimer()

            if currentFrame is None:
                break

            #
            # Calculate differences between current frame and last base of comparison
            #

            algPerformanceResults.framePrepAccumulator.OnStartTimer()
            currentComparison = PrepareFrameForAnalysis( currentFrame )
            algPerformanceResults.framePrepAccumulator.OnStopTimer()

            algPerformanceResults.rocAnalysisAccumulator.OnStartTimer()
            currentDiffCoefficient = CalculateDifferenceCoefficient( \
                self.baseOfComparison, currentComparison, currentFrame, self.args )
            motionDerivativeWasDetected = MotionDerivativeDetected( self.baseDiffCoefficient, currentDiffCoefficient )
            algPerformanceResults.rocAnalysisAccumulator.OnStopTimer()

            if motionDerivativeWasDetected:
            
                #
                # We found a frame which triggered the motion detection heuristic
                #

                # TODO-Pri1 voicua: use an iterator wrapper to hold onto the last 100 frames or so.
                # this will allow to jump back in time when analysis realizes it found some serious motion
                # especially after the accelerated (skipping) mode

                # TODO voicua: proper messaging
                # logger.PrintMessage( 'Number of changed pixel luminances: %i' % currentDiffCoefficient )

                self.baseDiffCoefficient = currentDiffCoefficient
                self.baseFrame = currentFrame
                self.baseOfComparison = currentComparison

                # Save the pixels for subsequent analysis
                self.BufferDetectedFrame( currentDetectedFrames, videoIter.CurrentIndex(), self.baseFrame )
        
                # Update compression (detection) statistics
                numLoopsUntriggered = 0
                self.frameSkip = 0   # if we were skipping frames, no more. We found motion.
                totalNumFramesTriggered += 1

            elif self.frameSkip < self.kMaxFrameSkip:
                numLoopsUntriggered += 1
                if numLoopsUntriggered > self.kNumLoopsUntriggeredThreshold:
                    # time to move faster through the video, only unchanged frames here
                    numLoopsUntriggered = 0
                    self.frameSkip += 8


            # Done processing of this frame
            algPerformanceResults.totalFramesProcessed += 1

            #
            # Inspect movie time compression performance, and skip this file if it cannot be analyzed by this algorithm
            #

            timeCompressionRatio = float( totalNumFramesTriggered ) / float( videoIter.CurrentIndex() )
            if videoIter.CurrentIndex() > kWarmUpFrameCount:
                if timeCompressionRatio > 0.95 or (timeCompressionRatio > 0.50 and timeCompressionRatio > prevTimeCompressionRatio): 
                    analysisAborted = True
                    break
                prevTimeCompressionRatio = timeCompressionRatio


            #
            # Update algorithm running time performance statistics
            #

            currentPercentageDone = float( videoIter.CurrentIndex() ) / float( totalFrames)
            currentTime = perf_counter()
            if currentTime - timerStart > 10 or framesProcessedPerSecond == 0:
                # recalculate statistics
                timeSpanReference = currentTime - timerStart
                framesProcessedPerSecond = int( (videoIter.CurrentIndex() - frameIndexStarted) / timeSpanReference )
                if not self.args is None and self.args.verboseRunningTime:
                    diskPercentage = int( 100.0 * algPerformanceResults.frameFetchingAccumulator.accumulator / timeSpanReference )
                    prepPercentage = int( 100.0 * algPerformanceResults.framePrepAccumulator.accumulator / timeSpanReference )
                    analysisPercentage = int( 100.0 * algPerformanceResults.rocAnalysisAccumulator.accumulator / timeSpanReference )
                    logger.PrintMessage()
                    logger.PrintMessage( "Algorithm FPS: %i (Frame fetching: %i%%, Frame preparation: %i%%, Analysis: %i%%)" \
                        % (framesProcessedPerSecond, diskPercentage, prepPercentage, analysisPercentage) )
                    print( "Total allocated memory: %s" % vh.FormatMemSize( psutil.Process().memory_info().rss ) )
                    
                # reset counters
                timerStart = currentTime
                frameIndexStarted = videoIter.CurrentIndex()
                algPerformanceResults.ResetPerfCounters()

            if self.frameSkip == 0:        
                print( "Frames completed: %i (%i%%, speed=%ifps), ratio = %.2f            " \
                    % (videoIter.CurrentIndex(), 100 * currentPercentageDone, framesProcessedPerSecond, timeCompressionRatio), end='\r' )
            else:
                print( "Frames completed: %i (%i%%, speed=%ifps), frameSkip = %i          " \
                    % (videoIter.CurrentIndex(), 100 * currentPercentageDone, framesProcessedPerSecond, self.frameSkip), end='\r' )

        # Update returned performance data
        algPerformanceResults.totalFramesTriggered = totalNumFramesTriggered
        algPerformanceResults.algorithmFPS = framesProcessedPerSecond

        if analysisAborted:
            currentDetectedFrames.clear()
            algPerformanceResults.analysisAborted = True
            logger.PrintMessage( 'Rate of Change algorithm cannot analyze this video file succesfully. Aborted.' )
            return

        self.FlushVideoData( currentDetectedFrames )

        logger.PrintMessage( '' )
        logger.PrintMessage( 'Number of frames processed: %i' % algPerformanceResults.totalFramesProcessed )
        logger.PrintMessage( 'Total number of frames found interesting: %i' % totalNumFramesTriggered )
        logger.PrintMessage( "Frame rate-of-change analysis done." )



    # returns the duration in seconds, of the output video
    def GetOutputLength( self ):
        return int( self.totalFrameOutputCount / 30 )

    def FinishAnalysis( self ):
        self.WriteVideoData()
        if not self.videoWriter is None:
            self.videoWriter.close()
            os.rename( self.kRocTemporaryFilePath, self.kRocAnalyzedFilePath )



# "Private" methods:

    def BufferDetectedFrame( self, currentDetectedFrames, indexInOriginalFile, framePixels ):
        currentDetectedFrames.append( (indexInOriginalFile, framePixels) )
        if len( currentDetectedFrames ) > self.kMaxFramesToBuffer:
            self.FlushVideoData( currentDetectedFrames )

    def FlushVideoData( self, incomingDetectedFrames ):
        self.detectedFrames.extend( incomingDetectedFrames )
        self.totalFrameOutputCount += len( incomingDetectedFrames )
        incomingDetectedFrames.clear()
        if len( self.detectedFrames ) < 30:
            return
        self.WriteVideoData()

    def WriteVideoData( self ):
        if len( self.detectedFrames ) == 0:
            return

        if self.videoWriter is None:
            if len( self.detectedFrames ) < 10:
                # Write pngs to disk.
                for (frameIndex, frame) in self.detectedFrames:
                    iio.imwrite( os.path.join( self.args.destFolder, \
                        #TODO-Pri0 voicua: depending on the second analysis phase, think more about numbering here.
                        #   e.g. use file index in addition to frameIndex, or maybe an absolute time unit.
                        self.videoAnalysisName + '_ROC_analyzed_frame_' + str( frameIndex ) + '.png' ), frame )
                # Return. No Video file needs to be created
                self.detectedFrames.clear()
                return

            if len( self.detectedFrames ) < 30:
                self.videoWriter = iio.get_writer( self.kRocTemporaryFilePath, fps = 10 )
            else:
                self.videoWriter = iio.get_writer( self.kRocTemporaryFilePath, fps = 30 )

        for (frameIndex, frame) in self.detectedFrames:
            self.videoWriter.append_data( frame )
        self.detectedFrames.clear()

    def RemoveOutput( self ):
        if os.path.isfile( self.kRocTemporaryFilePath ):
            os.remove( self.kRocTemporaryFilePath )
        if os.path.isfile( self.kRocAnalyzedFilePath ):
            os.remove( self.kRocAnalyzedFilePath )


# End class RateOfChangeAnalysis


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument( "videoFile", help = "path to the video file to analyze" )
    parser.add_argument( "--destFolder", type = str, default = ".",
        help = "optional destination folder for results of analysis. Default: current working directory" )
    parser.add_argument( "--verboseRunningTime", action = "store_true",
        help="enables display of running time performance split per phases of the algorithm" )
    parser.add_argument( "--highlightDiffs", action="store_true",
        help="if enabled highlights the pixel difference in the output" )
    parser.add_argument( "--onlyDiffs", action="store_true",
        help="if enabled only the differences are output" )

    args = parser.parse_args()
    if args.onlyDiffs:
        args.highlightDiffs = True

    rocAnalyzer = RateOfChangeAnalyzer( args, os.path.basename( args.videoFile ) )
    rocAnalyzer.AddVideoFileToAnalysis( args.videoFile, vh.Logger() )
    rocAnalyzer.FinishAnalysis()

#TODO-Pri1 voicua: mark on the frame when there was a fast forward
#TODO-Pri0 voicua: movement analysis (i.e. find objects with contiguous move, linear, accelerated, etc) 
#   similar to the NASA programming contest some years ago
# TODO-Pri0 voicua: noise detection + removal
# TODO-Pri1 voicua: assign AI/heuristics calculated interestingness scores to analysis, to prioritize review/notifications, etc
# TODO-Pri1 voicua: refine the roc algorithm by looking at the grid location, similar to the tile PSNR strategies