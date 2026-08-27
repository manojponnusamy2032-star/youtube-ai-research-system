---
id: knowledge-2f68db68
type: lesson
title: FFmpeg Stream Mapping Issue
created_at: 2026-08-24T15:23:02.727252+00:00
updated_at: 2026-08-24T15:23:02.727252+00:00
tags:
  - lesson
source: generated
---

# FFmpeg Stream Mapping Issue

## Problem

Audio was missing from output.

## Root Cause

Incorrect stream mapping.

## Solution

Use -map 0:a explicitly.

## Prevention

Always verify stream mapping.