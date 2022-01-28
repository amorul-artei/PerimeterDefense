# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      16.01.2022 voicua: Created "analyzeVideoUnitTest.py" to test algorithms used in the analyzeVideo script.

import numpy

import videoAnalyzeRateOfChange


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
    print( "Analysis aborted: " + str( results.analysisAborted ) )
    print( "Number of triggered frames: " + str( results.totalFramesTriggered ) )
    print( "Algorithm FPS: " + str( results.algorithmFPS ) )

def CheckResults( fileName, expected, obtained, stats ):
    # TODO voicua: FPS might not be exact enough, and dependent on the machine, etc.
    # perhaps check the statistics related to acceleration such as number of frames skipped
    if expected.analysisAborted != obtained.analysisAborted or \
        expected.totalFramesTriggered != obtained.totalFramesTriggered or \
        not videoAnalyzeRateOfChange.IsValueInRelativeInterval( expected.algorithmFPS, 0.35, obtained.algorithmFPS ):
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


# V2K: "se abereaza"
def PrintTitle( leasfiavutDejaAberate ):
    print()
    print( leasfiavutDejaAberate )  # Eu: "partea proasta este ca m-am aberat deja in proiectele mele anterioare,
        # dar o fecala infecta s-a bagat peste viata mea

class TestStatistics:
    def __init__( self ):
        self.numErrors = 0

def RunTestForVideoFile( fileName, stats ):
    PrintTitle( "Running test for file " + fileName )
    algPerformanceResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
    videoAnalyzeRateOfChange.runRateOfChangeAnalysis( fileName, None, algPerformanceResults )
    CheckResults( fileName, expectedResults, algPerformanceResults, stats )


print()
print( "Starting unitest:" )
print( "=================" )
print()

stats = TestStatistics()
Test_CalculateDifferenceCoefficient( stats )

expectedResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
expectedResults.analysisAborted = False
expectedResults.totalFramesTriggered = 1
expectedResults.algorithmFPS = 14
RunTestForVideoFile( unitTest0, stats )

expectedResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
expectedResults.analysisAborted = False
expectedResults.totalFramesTriggered = 1
expectedResults.algorithmFPS = 28
RunTestForVideoFile( unitTest1, stats )

expectedResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
expectedResults.analysisAborted = False
expectedResults.totalFramesTriggered = 24
expectedResults.algorithmFPS = 30
RunTestForVideoFile( unitTest2, stats )

if stats.numErrors == 0:
    print( "Unit test succeeded without errors!" )
