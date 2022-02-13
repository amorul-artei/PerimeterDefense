#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Author: Voicu Anton Albu
# Email: voicualbu@gmail.com
# Revision History:
#      08.02.2022 voicua: Created "audioAnalyze.py" to handle the audio extraction and spectrum analysis of the audio channel

import os
import argparse

import ffmpeg

import videoAnalysisHelpers


def runAudioAnalysis( videoPathName, logger, args ):
    logger.PrintMessage( "Audio analysis starting" )

    originalVideoFileName = os.path.basename( videoPathName )
    audioOutputFilePath = os.path.join( args.destFolder, originalVideoFileName + ".mp3" )

    try:
        # For now just extraction, and use a spectrum analysis app such as "Sonic Visualizer" to look at the data
        ffmpeg.input( videoPathName ).output( audioOutputFilePath, f = "mp3", vcodec = "none" ).run( overwrite_output = True )
    except:
        logger.PrintMessage( "Unable to extract audio." )    
    logger.PrintMessage( "Audio analysis done." )
    logger.PrintMessage()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument( "videoFile", help="path to the video file to analyze" )

    args = parser.parse_args()
    runAudioAnalysis( args.videoFile, videoAnalysisHelpers.Logger() )