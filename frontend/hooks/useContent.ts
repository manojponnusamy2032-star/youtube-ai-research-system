"use client";

import { useMutation } from '@tanstack/react-query';
import { generateContentPackage, ContentGenerationRequest } from '../services/contentClient';

export function useContentGeneration() {
  return useMutation((payload: ContentGenerationRequest) => generateContentPackage(payload));
}
