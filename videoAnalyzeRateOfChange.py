# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      14.01.2022 voicua: Created "analyzeVideo.py" to test algorithms used in the analyzeVideo script.
#      19.01.2022 voicua: Renamed to "videoAnalyzeRateOfChange.py" to better reflect what this phase of the algorithm is doing


import imageio as iio
import ffmpeg
from PIL import Image
from numpy import asarray
import numpy

import os
import sys
from time import perf_counter

kLuminanceDiffThreshold = 32
kMotionDerivativeThreshold = 20.0 # percentage of change in modified pixel count
kMinChange = 500

def PrepareFrameForAnalysis( frameRawData ):
    img = Image.fromarray( frameRawData, 'RGB' )
    img = img.convert( 'L' )
    return numpy.array( img, numpy.int16 )

def MotionDerivativeDetected( base, new ):
    if base < 0:
        return True

    if abs( new - base ) < kMinChange:
        return False

    threshold = float( base * kMotionDerivativeThreshold / 100.0 )
    return (new < base - threshold) or (new > base + threshold)

def CalculateDifferenceCoefficient( baseFrame, newFrame ):
    diff = (newFrame - baseFrame)
    numpy.divide( diff, kLuminanceDiffThreshold, out = diff, casting = 'unsafe' )
    return numpy.count_nonzero( diff )


def runRateOfChangeAnalysis( videoFileName ):
    kRocAnalyzedFileName = videoFileName + '_ROC_analyzed.mp4'
    if not os.path.isfile( videoFileName ):
        print( 'File not found: ' + videoFileName )
        return

    # get video properties such as number of frames, duration, etc
    videoMeta = ffmpeg.probe( videoFileName )[ "streams" ]

    print( 'Average Frame Rate: ' + videoMeta[ 0 ][ 'avg_frame_rate' ] )
    print( 'Duration in seconds: ' + videoMeta[ 0 ][ 'duration' ] )

    frameRatePair = videoMeta[ 0 ][ 'avg_frame_rate' ].split( '/' )
    frameRate = float( frameRatePair[ 0 ] ) / float( frameRatePair[ 1 ] )

    totalFrames = int( frameRate * float( videoMeta[ 0 ][ 'duration' ] ) )
    print( 'Total frames: %i' % totalFrames )

    reader = iio.get_reader( videoFileName )
    framesToSaveAsPng = []
    writer = None

    # Accelerate processing of the video, by skipping frames if there are no triggers detected for some time
    # This is an optimization, to compensate for the really slow Python algorithms/image libraries.
    kNumLoopsUntriggeredThreshold = 100
    numLoopsUntriggered = 0 # currently, this means there are no changes in the rate of changes
    kMaxFrameSkip = 24
    frameSkip = 0
    totalNumFramesTriggered = 0

    # Time Compression statistics, used to abort analysis if the frames are changing all the time, in unpredictable ways
    timeCompressionRatio = 0.0
    prevTimeCompressionRatio = 0.0
    analysisAborted = False

    currentFrameIndex = 0
    lastUpdatePercentage = 0
    iter = reader.iter_data()

    baseFrame = next( iter )
    baseOfComparison = PrepareFrameForAnalysis( baseFrame )
    baseDiffCoefficient = -1

    timerStart = perf_counter()
    frameIndexStarted = 0
    framesProcessedPerSecond = 0

    while not (baseOfComparison is None):

        # Read the next frame. Skip some frames if we are in skipping mode (i.e. uninteresting portion of the video)
        numFramesRead = 0
        while numFramesRead <= frameSkip:
            currentFrame = next( iter, None )
            if currentFrame is None:
                break
            currentFrameIndex += 1
            numFramesRead += 1

        if currentFrame is None:
            break

        # Calculate differences
        currentComparison = PrepareFrameForAnalysis( currentFrame )
        currentDiffCoefficient = CalculateDifferenceCoefficient( baseOfComparison, currentComparison )

        if MotionDerivativeDetected( baseDiffCoefficient, currentDiffCoefficient ):
        
            #
            # We found a frame which triggered the motion detection heuristic
            #

            # TODO voicua: proper messaging
            # print( 'Number of changed pixel luminances: %i' % currentDiffCoefficient )

            baseDiffCoefficient = currentDiffCoefficient
            baseFrame = currentFrame
            baseOfComparison = currentComparison

            # Save the pixels for subsequent analysis
            if writer is None:
                if len( framesToSaveAsPng ) < 10:
                    # Save to PNG list
                    framesToSaveAsPng.append( (currentFrameIndex, baseFrame) )

                else:
                    # Get rid of the PNG list, and start a video.
                    writer = iio.get_writer( kRocAnalyzedFileName, fps=10 )
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


        #
        # Inspect time compression performance, and skip this file if it cannot be analyzed by this algorithm
        #

        if currentFrameIndex > 2 * 60 * frameRate:
            timeCompressionRatio = float( totalNumFramesTriggered ) / float( currentFrameIndex )
            if timeCompressionRatio > 0.95 or (timeCompressionRatio > 0.50 and timeCompressionRatio > prevTimeCompressionRatio): 
                analysisAborted = True
                break
            prevTimeCompressionRatio = timeCompressionRatio


        #
        # Update time performance statistics
        #

        currentPercentageDone = float( currentFrameIndex ) / float( totalFrames)
        currentTime = perf_counter()
        if currentTime - timerStart > 10 or framesProcessedPerSecond == 0:
            # recalculate statistics
            framesProcessedPerSecond = int( (currentFrameIndex - frameIndexStarted) / (currentTime - timerStart) )
            # reset counters
            timerStart = currentTime
            frameIndexStarted = currentFrameIndex

        if frameSkip == 0:        
            print( "Frames completed: %i (%i%%, speed=%ifps), ratio = %.2f" % (currentFrameIndex, 100 * currentPercentageDone, framesProcessedPerSecond, timeCompressionRatio), end='\r' )
        else:
            print( "Frames completed: %i (%i%%, speed=%ifps), frameSkip = %i" % (currentFrameIndex, 100 * currentPercentageDone, framesProcessedPerSecond, frameSkip), end='\r' )

    if not writer is None:
        writer.close()

    if analysisAborted:
        print( 'Rate of Change algorithm cannot analyze this video succesfully. Aborted.' )
        if os.path.isfile( kRocAnalyzedFileName ):
            os.remove( kRocAnalyzedFileName )
        return


    # TODO voicua: instead of saving 10 files, would it be better if it's possible to create a video with very low frame rate 5fps?
    if not framesToSaveAsPng is None:
        # Write png to disk. TODO: command line parameter
        for (frameIndex, frame) in framesToSaveAsPng:
            iio.imwrite( videoFileName + '_ROC_analyzed_frame_' + str( frameIndex ) + '.png', frame )

    #if totalNumFramesTriggered < 10:
        #print( "Removing file " + videoFileName + " due to few triggered frames found. Triggered frames were saved." )
        #os.remove( videoFileName )


    print( '' )
    print( 'All Done. Number of frames processed: %i' % currentFrameIndex )
    print( 'Total number of frames found interesting: %i' % totalNumFramesTriggered )



if __name__ == "__main__":
    runRateOfChangeAnalysis( sys.argv[ 1 ] )

