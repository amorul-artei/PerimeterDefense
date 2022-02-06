#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      19.01.2022 voicua: Created "processVideos.py" to run analysis on a directory

import os
import time
import argparse

import ffmpeg

import videoAnalyzeRateOfChange
from videoAnalysisHelpers import Logger


def GetFormattedFileSize( size ):
    sizeInGb = float( size ) / (1024.0 * 1024.0 * 1024.0)
    return "{:.2f}GiB".format( sizeInGb )

def GetFormattedFileStats( f ):
    return f[ 0 ] + ', ' + \
        time.strftime( '%Y.%m.%d %H:%M:%S', time.localtime( f[ 1 ] ) ) + ', ' + \
        GetFormattedFileSize( f[ 2 ] )

def WithinRange( v1, v2, r ):
    return abs( v2 - v1 ) <= r

def AnalyzeTimeline( videosList ):
    expectedCreationTime = 0
    for f in videosList:
        # Check if current start time fits expected range
        if expectedCreationTime > 0:
            if not WithinRange( expectedCreationTime, f[ 1 ], 1 ):
                print( f[ 0 ] + " started with delay of " + str( f[ 1 ] - expectedCreationTime ) + " seconds" )
        videoMeta = ffmpeg.probe( f[ 0 ] )[ "streams" ]

        duration = videoMeta[ 0 ][ 'duration' ]
        expectedCreationTime = f[ 1 ] + duration


def CleanupPreviousRun():
    filesToRemove = [ f for f in os.listdir() if os.path.isfile( f ) and \
        f.lower().startswith( videoAnalyzeRateOfChange.kTempFilePrefix.lower() ) ]
    print( "Removing %i temporary files from previous run..." % len( filesToRemove ) )
    for f in filesToRemove:
        os.remove( f )


def DoGoProSpecificCleanup():
    # Remove all *lrv and *thm files
    filesToRemove = [ f for f in os.listdir() if os.path.isfile( f ) and \
        ( f.lower().endswith( ".lrv" ) or f.lower().endswith( ".thm" ) ) ]
    print( "Removing %i GoPro low resolution videos..." % len( filesToRemove ) )
    for f in filesToRemove:
        os.remove( f )

    # Rename all *.360 to *.360.mp4
    filesToRename = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".360" ) ]
    print( "Renaming %i 360 GoPro videos so that imageio accepts them..." % len( filesToRename ) )
    for f in filesToRename:
        os.rename( f, f + ".mp4" )




def runProcessVideos( args = None ):

    #
    # Prepare the folder for a new analysis, by doing some initial maintenance
    #
    CleanupPreviousRun()
    DoGoProSpecificCleanup()

    #
    # Calculate the list of videos that must be processed. Remove from the list any videos already analyzed.
    # This in turn enables the user to restart the process on a previously interrupted run.
    #

    onlyVideos = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".mp4" ) ]

    rocPreviousResults = [ f for f in onlyVideos if "_ROC_analyzed" in f ]
    allTextFiles = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".txt" ) ]

    # initialize the list with all the originals found in the folder
    tobeAnalyzedVideos = list( set( onlyVideos ) - set( rocPreviousResults ) )

    alreadyAnalyzedOriginals = []
    for f in rocPreviousResults:
        origName = f[ :f.find( "_ROC_analyzed" ) ]
        print( origName )
        alreadyAnalyzedOriginals.append( origName )

    for f in allTextFiles:
        origName = os.path.splitext( os.path.basename( f ) )[ 0 ]
        if origName in tobeAnalyzedVideos:
            alreadyAnalyzedOriginals.append( origName )

    if len( alreadyAnalyzedOriginals ) > 0:
        print( "Found previous analysis, skipping the following originals:" )
        for f in alreadyAnalyzedOriginals:
            print( f )


    tobeAnalyzedVideos = list( set( tobeAnalyzedVideos ) - set( alreadyAnalyzedOriginals ) )

    #
    # Add aditional file information to the final list, and sort it
    #

    tobeAnalyzedVideos = [ (f, os.path.getmtime( f ), os.path.getsize( f ) ) for f in tobeAnalyzedVideos ]
    tobeAnalyzedVideos.sort( key = lambda x: x[ 1 ] )

    for f in tobeAnalyzedVideos:
        print( GetFormattedFileStats( f ) )

    print( "A total of %i videos to analyze" % len( tobeAnalyzedVideos ) )

    #AnalyzeTimeline( tobeAnalyzedVideos )

    #
    # Run analysis
    #

    count = 1
    for a in tobeAnalyzedVideos:
        print( "" )
        print( "" )
        print( "------------------------------------------------------" )
        print( "-----------------------%i/%i--------------------------" % (count, len( tobeAnalyzedVideos )) )

        logger = Logger( a[ 0 ] + ".txt" )
        print( "Running analysis for " + GetFormattedFileStats( a ) )
        videoAnalyzeRateOfChange.runRateOfChangeAnalysis( a[ 0 ], logger, args )
        logger.Close()

        print( "" )
        count += 1


    print( "" )
    print( "All done." )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument( "--verboseRunningTime", \
        help="enables display of running time performance split per phases of the algorithm", action="store_true" )

    args = parser.parse_args()
    runProcessVideos( args )


#TODO-Pri1 voicua: ability to carbon copy all output to a log file as well
#TODO-Pri0 voicua: unittesting for this file
