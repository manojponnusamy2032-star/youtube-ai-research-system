---
id: knowledge-706b62a4
type: lesson
title: FFmpeg Stream Mapping Issue
created_at: 2026-08-21T08:22:30.446129+00:00
updated_at: 2026-08-21T08:22:30.446129+00:00
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