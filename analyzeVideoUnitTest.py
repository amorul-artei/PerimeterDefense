# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      16.01.2022 voicua: Created "analyzeVideoUnitTest.py" to test algorithms used in the analyzeVideo script.

import numpy

from videoAnalyzeRateOfChange import CalculateDifferenceCoefficient


def Call_CalculateDifferenceCoefficient( baseFrame, newFrame, expectedResult ):
    res = CalculateDifferenceCoefficient( baseFrame, newFrame )
    print( "Difference Coefficient Obtained = " + str( res ) )
    if res != expectedResult:
        print( "         Error! Expected result was: " + str( expectedResult ) )
    
def Test_CalculateDifferenceCoefficient():
    baseFrame = numpy.array( [[0, 0, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    newFrame = numpy.array( [[0, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    expectedResult = 0
    Call_CalculateDifferenceCoefficient( baseFrame, newFrame, expectedResult )

    baseFrame = numpy.array( [[0, 0, 0, 0], [0, 255, 255, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    newFrame = numpy.array( [[0, 0, 0, 0], [0, 0, 60, 0], [0, 0, 0, 0], [0, 0, 0, 0]], dtype=numpy.int16 )
    expectedResult = 2
    Call_CalculateDifferenceCoefficient( baseFrame, newFrame, expectedResult )
    
    


print( "Starting unitest:" )
Test_CalculateDifferenceCoefficient()
