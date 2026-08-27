---
id: knowledge-07083cdd
type: lesson
title: FFmpeg Stream Mapping Issue
created_at: 2026-08-24T15:30:44.058182+00:00
updated_at: 2026-08-24T15:30:44.058182+00:00
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