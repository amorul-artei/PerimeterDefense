#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      19.01.2022 voicua: Created "processVideos.py" to run analysis on a directory

import os
import shutil
import time
import argparse

import ffmpeg

import audioAnalyze
import videoAnalyzeRateOfChange
from videoAnalysisHelpers import Logger

kTempLogFilePrefix = "temp_logfile_"

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


def CleanupPreviousRun( destFolder ):
    filesToRemove = [ f for f in os.listdir( destFolder ) if os.path.isfile( os.path.join( destFolder, f ) ) and \
        ( f.lower().startswith( videoAnalyzeRateOfChange.kTempFilePrefix.lower() ) or \
          f.lower().startswith( kTempLogFilePrefix.lower() ) ) ]
    print( destFolder )
    print( os.listdir( destFolder ) )
    print( "Removing %i temporary files from previous run..." % len( filesToRemove ) )
    for f in filesToRemove:
        os.remove( os.path.join( destFolder, f ) )


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

def DoGarminSpecificCleanup():
    # Remove all *.glv
    filesToRemove = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".glv" ) ]
    print( "Removing %i Garmin low resolution videos..." % len( filesToRemove ) )
    for f in filesToRemove:
        os.remove( f )


def IsVideoFile( fileName, withNameDecorator ):
    return os.path.isfile( fileName ) and fileName.lower().endswith( ".mp4" ) and ( withNameDecorator in fileName )

def runProcessVideos( args ):

    #
    # Prepare the folder for a new analysis, by doing some initial maintenance
    #
    CleanupPreviousRun( args.destFolder )
    DoGoProSpecificCleanup()
    DoGarminSpecificCleanup()

    #
    # Calculate the list of videos that must be processed. Remove from the list any videos already analyzed.
    # This in turn enables the user to restart the process on a previously interrupted run.
    #

    allSourceVideos = [ f for f in os.listdir() if os.path.isfile( f ) and f.lower().endswith( ".mp4" ) ]

    rocPreviousResults = [ f for f in os.listdir( args.destFolder ) if IsVideoFile( f, "_ROC_analyzed" ) ]
    allTextFiles = [ f for f in os.listdir( args.destFolder ) if os.path.isfile( f ) and f.lower().endswith( ".txt" ) ]

    # initialize the list with all the originals found in the folder
    tobeAnalyzedVideos = list( set( allSourceVideos ) - set( rocPreviousResults ) )

    alreadyAnalyzedOriginals = []
    for f in allTextFiles:
        origName = os.path.splitext( os.path.basename( f ) )[ 0 ]
        if origName in tobeAnalyzedVideos:
            alreadyAnalyzedOriginals.append( origName )

    # Remove originals with existing results, even if incomplete analysis, to avoid stealth overwriting of the results
    # Previous results must be explicitly removed by the user
    for f in rocPreviousResults:
        origName = f[ :f.find( "_ROC_analyzed" ) ]
        alreadyAnalyzedOriginals.append( origName )

    alreadyAnalyzedOriginals = set( alreadyAnalyzedOriginals )

    if len( alreadyAnalyzedOriginals ) > 0:
        print( "Found previous analysis, skipping the following %i originals:" % len( alreadyAnalyzedOriginals ) )
        for f in alreadyAnalyzedOriginals:
            print( f )


    tobeAnalyzedVideos = list( set( tobeAnalyzedVideos ) - alreadyAnalyzedOriginals )

    #
    # Add aditional file information to the final list, and sort it
    #

    tobeAnalyzedVideos = [ (f, os.path.getmtime( f ), os.path.getsize( f ) ) for f in tobeAnalyzedVideos ]
    tobeAnalyzedVideos.sort( key = lambda x: x[ 1 ] )

    print( "" )
    print( "The following video files will be analyzed:" )

    for f in tobeAnalyzedVideos:
        print( GetFormattedFileStats( f ) )

    print( "A total of %i videos to analyze" % len( tobeAnalyzedVideos ) )

    #AnalyzeTimeline( tobeAnalyzedVideos )

    #
    # Run analysis
    #

    analyzedFolderName = "AnalyzedVideos"
    if not os.path.exists( analyzedFolderName ):
        os.mkdir( analyzedFolderName )

    count = 1
    for a in tobeAnalyzedVideos:
        print( "" )
        print( "" )
        print( "------------------------------------------------------" )
        print( "-----------------------%i/%i--------------------------" % (count, len( tobeAnalyzedVideos )) )

        tempLoggingFilePath = os.path.join( args.destFolder, kTempLogFilePrefix + a[ 0 ] + ".txt" )
        logger = Logger( tempLoggingFilePath )
        logger.PrintMessage( "Running analysis for " + GetFormattedFileStats( a ) )

        algPerformanceResults = videoAnalyzeRateOfChange.AlgorithmPerformanceResults()
        errorProcessing = False

        # audio analysis
        audioAnalyze.runAudioAnalysis( a[ 0 ], logger, args )

        # rate of change analysis
        videoAnalyzeRateOfChange.runRateOfChangeAnalysis( a[ 0 ], logger, args, algPerformanceResults )

        logger.Close()
        os.rename( tempLoggingFilePath, os.path.join( args.destFolder, a[ 0 ] + ".txt" ) )

        if not ( errorProcessing or algPerformanceResults.analysisAborted ):
            # move video to "analyzed"
            shutil.move( a[ 0 ], analyzedFolderName + os.sep + a[ 0 ] )

        print( "" )
        count += 1


    print( "" )
    print( "All done." )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument( "--destFolder", type = str, default = ".",
        help = "optional destination folder for results of analysis. Default: current working directory" )
    parser.add_argument( "--verboseRunningTime", action = "store_true",
        help = "enables display of running time performance split per phases of the algorithm" )

    args = parser.parse_args()

    runProcessVideos( args )


#TODO-Pri1 voicua: ability to carbon copy all output to a log file as well
#TODO-Pri0 voicua: unittesting for this file
#TODO-Pri0 voicua: email notifications
#TODO-Pri2 voicua: adaptive sampling rate: categorize videos, assign optimal speeds to those categories, 
#   challenge the speeds by going slower on purpose, to see if movements are missed.
#TODO-Pri0 voicua: save all videos with lower resolution, dropped frame rate, reencoded for compression
#TODO-Pri0 voicua: overall performance metrics, measured in raw source bytes per second processed.
#TODO-Pri0 voicua: copy  source file to memory and do all read operations from there, to read only once (4GB files, etc)
#TODO-Pri2 voicua: overflow folder for disk full


#TODO-Pri0 voicua: python script to quickly format SD cards, by choosing entry number (list df -h, skip system or protected)
