#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      14.01.2022 voicua: Created "analyzeVideo.py" to test algorithms used in the analyzeVideo script.
#      19.01.2022 voicua: Renamed to "videoAnalyzeRateOfChange.py" to better reflect what this phase of the algorithm is doing
#      28.01.2022 voicua: Added parameter to enable highlighting the changes, to help with the tuning


import imageio as iio
import ffmpeg
from PIL import Image
import numpy

import os
import sys
from time import perf_counter
import argparse

import videoAnalysisHelpers

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
        self.counter = 0

    def OnStartTimer( self ):
        self.counter = perf_counter()

    def OnStopTimer( self ):
        stopTime = perf_counter()
        self.accumulator += (stopTime - self.counter)

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
        self.diskReadingAccumulator = RunningTimeAccumulator()
        self.framePrepAccumulator = RunningTimeAccumulator()
        self.rocAnalysisAccumulator = RunningTimeAccumulator()



def runRateOfChangeAnalysis( videoPathName, logger, args, algPerformanceResults = None ):
    if algPerformanceResults is None:
        algPerformanceResults = AlgorithmPerformanceResults()

    # Figure out disk locations first
    if not os.path.isfile( videoPathName ):
        print( 'File not found: ' + videoPathName )
        return

    originalVideoFileName = os.path.basename( videoPathName )
    kRocTemporaryFilePath = os.path.join( args.destFolder, kTempFilePrefix + originalVideoFileName )
    kRocAnalyzedFilePath = os.path.join( args.destFolder, originalVideoFileName + '_ROC_analyzed.mp4' )

    # get video properties such as number of frames, duration, etc
    videoMeta = ffmpeg.probe( videoPathName )[ "streams" ]

    logger.PrintMessage( "Frame rate-of-change analysis starting" )
    logger.PrintMessage( 'Resolution: %ix%i' % (videoMeta[ 0 ][ 'width' ], videoMeta[ 0 ][ 'height' ]) )
    logger.PrintMessage( 'Average Frame Rate: ' + videoMeta[ 0 ][ 'avg_frame_rate' ] )
    logger.PrintMessage( 'Duration in seconds: ' + videoMeta[ 0 ][ 'duration' ] )

    frameRatePair = videoMeta[ 0 ][ 'avg_frame_rate' ].split( '/' )
    frameRate = float( frameRatePair[ 0 ] ) / float( frameRatePair[ 1 ] )

    totalFrames = int( frameRate * float( videoMeta[ 0 ][ 'duration' ] ) )
    logger.PrintMessage( 'Total frames: %i' % totalFrames )
    algPerformanceResults.totalFramesInVideoFile = totalFrames

    reader = iio.get_reader( videoPathName )
    framesToSaveAsPng = []
    writer = None

    # Accelerate processing of the video, by skipping frames if there are no triggers detected for some time
    # This is an optimization, to compensate for the really slow Python algorithms/image libraries.
    kNumLoopsUntriggeredThreshold = 100
    numLoopsUntriggered = 0 # currently, this means there are no changes in the rate of changes
    kMaxFrameSkip = 30
    frameSkip = 0
    totalNumFramesTriggered = 0

    # Time Compression statistics, used to abort analysis if the frames are changing all the time, in unpredictable ways
    timeCompressionRatio = 0.0
    prevTimeCompressionRatio = 0.0
    analysisAborted = False

    currentFrameIndex = 0
    
    #iter = reader.iter_data()

    baseFrame = reader.get_next_data()
    baseOfComparison = PrepareFrameForAnalysis( baseFrame )
    baseDiffCoefficient = -1

    timerStart = perf_counter()
    frameIndexStarted = 0
    framesProcessedPerSecond = 0

    while not (baseOfComparison is None):

        # Read the next frame. Skip some frames if we are in skipping mode (i.e. uninteresting portion of the video)
        if currentFrameIndex + frameSkip >= totalFrames:
            break   # end of the video. TODO voicua: consider to always process the last few frames (i.e. disable frameSkip if on)

        algPerformanceResults.diskReadingAccumulator.OnStartTimer()

        currentFrame = None

        try:
            if frameSkip > 0:
                reader.set_image_index( currentFrameIndex + frameSkip )
                currentFrameIndex += frameSkip
                algPerformanceResults.totalFramesSkipped += frameSkip

            currentFrame = reader.get_next_data()
            currentFrameIndex += 1

            '''
            # The following strategy for skipping frames is slower, to avoid
            numFramesRead = 0
            while numFramesRead <= frameSkip:
                currentFrame = next( iter, None )
                if currentFrame is None:
                    break
                currentFrameIndex += 1
                numFramesRead += 1
            '''
        except:
            logger.PrintMessage( "Exception thrown by video decoder attempting to read frame index %i" % currentFrameIndex )
            # TODO-Pri1 voicua: what if the file support media was unplugged?
            logger.PrintMessage( "Assuming end of file. Ending analysis." )

        algPerformanceResults.diskReadingAccumulator.OnStopTimer()

        if currentFrame is None:
            break

        #
        # Calculate differences
        #

        algPerformanceResults.framePrepAccumulator.OnStartTimer()
        currentComparison = PrepareFrameForAnalysis( currentFrame )
        algPerformanceResults.framePrepAccumulator.OnStopTimer()

        algPerformanceResults.rocAnalysisAccumulator.OnStartTimer()
        currentDiffCoefficient = CalculateDifferenceCoefficient( \
            baseOfComparison, currentComparison, currentFrame, args )
        motionDerivativeWasDetected = MotionDerivativeDetected( baseDiffCoefficient, currentDiffCoefficient )
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

            baseDiffCoefficient = currentDiffCoefficient
            baseFrame = currentFrame
            baseOfComparison = currentComparison

            # Save the pixels for subsequent analysis
            if writer is None:
                if len( framesToSaveAsPng ) < 30:
                    # Save to PNG list
                    framesToSaveAsPng.append( (currentFrameIndex, baseFrame) )

                else:
                    # Get rid of the PNG list, and start a video.
                    writer = iio.get_writer( kRocTemporaryFilePath, fps = 30 )
                    for (frameIndex, frame) in framesToSaveAsPng:
                        writer.append_data( baseFrame )
                        
                    framesToSaveAsPng = None
                    writer.append_data( baseFrame )

            else:
                writer.append_data( baseFrame )
    
            # Update compression (detection) statistics
            numLoopsUntriggered = 0
            frameSkip = 0   # if we were skipping frames, no more. We found motion.
            totalNumFramesTriggered += 1

        elif frameSkip < kMaxFrameSkip:
            numLoopsUntriggered += 1
            if numLoopsUntriggered > kNumLoopsUntriggeredThreshold:
                # time to move faster through the video, only unchanged frames here
                numLoopsUntriggered = 0
                frameSkip += 8


        # Done processing of this frame
        algPerformanceResults.totalFramesProcessed += 1

        #
        # Inspect movie time compression performance, and skip this file if it cannot be analyzed by this algorithm
        #

        timeCompressionRatio = float( totalNumFramesTriggered ) / float( currentFrameIndex )
        if currentFrameIndex > 2 * 60 * frameRate:
            if timeCompressionRatio > 0.95 or (timeCompressionRatio > 0.50 and timeCompressionRatio > prevTimeCompressionRatio): 
                analysisAborted = True
                break
            prevTimeCompressionRatio = timeCompressionRatio


        #
        # Update algorithm running time performance statistics
        #

        currentPercentageDone = float( currentFrameIndex ) / float( totalFrames)
        currentTime = perf_counter()
        if currentTime - timerStart > 10 or framesProcessedPerSecond == 0:
            # recalculate statistics
            timeSpanReference = currentTime - timerStart
            framesProcessedPerSecond = int( (currentFrameIndex - frameIndexStarted) / timeSpanReference )
            if not args is None and args.verboseRunningTime:
                diskPercentage = int( 100.0 * algPerformanceResults.diskReadingAccumulator.accumulator / timeSpanReference )
                prepPercentage = int( 100.0 * algPerformanceResults.framePrepAccumulator.accumulator / timeSpanReference )
                analysisPercentage = int( 100.0 * algPerformanceResults.rocAnalysisAccumulator.accumulator / timeSpanReference )
                logger.PrintMessage()
                logger.PrintMessage( "Algorithm FPS: %i (Disk reading: %i%%, Frame preparation: %i%%, Analysis: %i%%)" \
                    % (framesProcessedPerSecond, diskPercentage, prepPercentage, analysisPercentage) )
            # reset counters
            timerStart = currentTime
            frameIndexStarted = currentFrameIndex
            algPerformanceResults.ResetPerfCounters()

        if frameSkip == 0:        
            print( "Frames completed: %i (%i%%, speed=%ifps), ratio = %.2f            " \
                % (currentFrameIndex, 100 * currentPercentageDone, framesProcessedPerSecond, timeCompressionRatio), end='\r' )
        else:
            print( "Frames completed: %i (%i%%, speed=%ifps), frameSkip = %i          " \
                % (currentFrameIndex, 100 * currentPercentageDone, framesProcessedPerSecond, frameSkip), end='\r' )

    if not writer is None:
        writer.close()
        # Rename file to final name
        os.rename( kRocTemporaryFilePath, kRocAnalyzedFilePath )

    # Update returned performance data
    algPerformanceResults.totalFramesTriggered = totalNumFramesTriggered
    algPerformanceResults.algorithmFPS = framesProcessedPerSecond

    if analysisAborted:
        algPerformanceResults.analysisAborted = True
        logger.PrintMessage( 'Rate of Change algorithm cannot analyze this video succesfully. Aborted.' )
        if os.path.isfile( kRocAnalyzedFilePath ):
            os.remove( kRocAnalyzedFilePath )
        return


    if not framesToSaveAsPng is None:
        if len( framesToSaveAsPng ) >= 10:
            writer = iio.get_writer( kRocTemporaryFilePath, fps = 10 )
            for (frameIndex, frame) in framesToSaveAsPng:
                writer.append_data( baseFrame )
            writer.close()
            os.rename( kRocTemporaryFilePath, kRocAnalyzedFilePath )
        else:
            # Write pngs to disk.
            for (frameIndex, frame) in framesToSaveAsPng:
                iio.imwrite( os.path.join( args.destFolder, \
                    originalVideoFileName + '_ROC_analyzed_frame_' + str( frameIndex ) + '.png' ), frame )


    logger.PrintMessage( '' )
    logger.PrintMessage( 'All Done. Number of frames processed: %i' % algPerformanceResults.totalFramesProcessed )
    logger.PrintMessage( 'Total number of frames found interesting: %i' % totalNumFramesTriggered )
    logger.PrintMessage( "Frame rate-of-change analysis done." )



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

    runRateOfChangeAnalysis( args.videoFile, videoAnalysisHelpers.Logger(), args )

#TODO-Pri1 voicua: mark on the frame when there was a fast forward
#TODO-Pri0 voicua: movement analysis (i.e. find objects with contiguous move, linear, accelerated, etc) 
#   similar to the NASA programming contest some years ago
# TODO-Pri0 voicua: noise detection + removal
# TODO-Pri1 voicua: assign AI/heuristics calculated interestingness scores to analysis, to prioritize review/notifications, etc
# TODO-Pri1 voicua: refine the roc algorithm by looking at the grid location, similar to the tile PSNR strategies
