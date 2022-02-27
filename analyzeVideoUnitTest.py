#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      16.01.2022 voicua: Created "analyzeVideoUnitTest.py" to test algorithms used in the analyzeVideo script.

import os
import argparse

import numpy

import videoAnalyzeRateOfChange
import videoAnalysisHelpers


unitTestDataPath = "../UnitTestData/"
unitTest0 = unitTestDataPath + "UnitTest0.mp4"
unitTest1 = unitTestDataPath + "UnitTest1.mp4"
unitTest2 = unitTestDataPath + "UnitTest2.mp4"


def Call_CalculateDifferenceCoefficient( baseFrame, newFrame, expectedResult, stats ):
    res = videoAnalyzeRateOfChange.CalculateDifferenceCoefficient( baseFrame, newFrame )
    print( "Difference Coefficient Obtained = " + str( res ) )
    if res != expectedResult:
        stats.numErrors += 1
        print( "         Error! Expected result was: " + str( expectedResult ) )
    
def Test_CalculateDifferenceCoefficient( stats ):
    baseFrame = numpy.array( [[0, 0, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    newFrame = numpy.array( [[0, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    expectedResult = 0
    Call_CalculateDifferenceCoefficient( baseFrame, newFrame, expectedResult, stats )

    baseFrame = numpy.array( [[0, 0, 0, 0], [0, 255, 255, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    newFrame = numpy.array( [[0, 0, 0, 0], [0, 0, 60, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    expectedResult = 2
    Call_CalculateDifferenceCoefficient( baseFrame, newFrame, expectedResult, stats )
    

def PrintPerf( results ):
    spaceSuffix = "    "
    print( spaceSuffix + "Analysis aborted: " + str( results.analysisAborted ) )
    print( spaceSuffix + "Number of frames expected in the file: " + str( results.totalFramesInVideoFile ) )
    print( spaceSuffix + "Number of processed frames: " + str( results.totalFramesProcessed ) )
    print( spaceSuffix + "Number of skipped frames: " + str( results.totalFramesSkipped ) )
    print( spaceSuffix + "Number of triggered frames: " + str( results.totalFramesTriggered ) )
    print( spaceSuffix + "Algorithm FPS: " + str( results.algorithmFPS ) )

def CheckResults( fileName, expected, obtained, stats ):
    if expected.analysisAborted != obtained.analysisAborted or \
        expected.totalFramesInVideoFile != obtained.totalFramesInVideoFile or \
        expected.totalFramesProcessed != obtained.totalFramesProcessed or \
        expected.totalFramesSkipped != obtained.totalFramesSkipped or \
        expected.totalFramesTriggered != obtained.totalFramesTriggered:
            print( "Algorithm performance changed for file: ", fileName )
            print( "Expected results:" )
            PrintPerf( expected )
            print( "Obtained results:" )
            PrintPerf( obtained )
            stats.numErrors += 1
            return False
    else:
        print( "UnitTest for file ", fileName, " run succesfully" )

    return True


def PrintTitle( title ):
    print()
    print( title )

class TestStatistics:
    def __init__( self ):
        self.numErrors = 0

def RunTestForVideoFile( fileName, args, stats ):
    PrintTitle( "Running test for file " + fileName )

    logger = videoAnalysisHelpers.Logger()
    algPerformanceResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
    rocAnalyzer = videoAnalyzeRateOfChange.RateOfChangeAnalyzer( args, os.path.basename( fileName ) )
    rocAnalyzer.AddVideoFileToAnalysis( fileName, logger, algPerformanceResults )

    CheckResults( fileName, expectedResults, algPerformanceResults, stats )


print()
print( "Starting unitest:" )
print( "=================" )
print()

stats = TestStatistics()
Test_CalculateDifferenceCoefficient( stats )

parser = argparse.ArgumentParser()
parser.add_argument( "--destFolder", type = str, default = ".",
    help = "optional destination folder for results of analysis. Default: current working directory" )
parser.add_argument( "--verboseRunningTime", action="store_true",
    help="enables display of running time performance split per phases of the algorithm" )
parser.add_argument( "--highlightDiffs", action="store_true",
    help="if enabled highlights the pixel difference in the output" )
parser.add_argument( "--onlyDiffs", action="store_true",
    help="if enabled only the differences are output" )

args = parser.parse_args( "" )

expectedResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
expectedResults.analysisAborted = False
expectedResults.totalFramesInVideoFile = 240
expectedResults.totalFramesProcessed = 119
expectedResults.totalFramesSkipped = 120
expectedResults.totalFramesTriggered = 1
expectedResults.algorithmFPS = 33
RunTestForVideoFile( unitTest0, args, stats )

expectedResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
expectedResults.analysisAborted = False
expectedResults.totalFramesInVideoFile = 480
expectedResults.totalFramesProcessed = 151
expectedResults.totalFramesSkipped = 328
expectedResults.totalFramesTriggered = 1
expectedResults.algorithmFPS = 47
RunTestForVideoFile( unitTest1, args, stats )

expectedResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
expectedResults.analysisAborted = False
expectedResults.totalFramesInVideoFile = 939
expectedResults.totalFramesProcessed = 426
expectedResults.totalFramesSkipped = 512
expectedResults.totalFramesTriggered = 24
expectedResults.algorithmFPS = 42
RunTestForVideoFile( unitTest2, args, stats )

print()
if stats.numErrors == 0:
    print( "Unit test succeeded without errors!" )
else:
    print( "Unit test found %i errors!" % stats.numErrors )

print()
print()
