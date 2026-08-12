"use client";

import { useQuery } from '@tanstack/react-query';
import { fetchPatterns } from '../services/patternsClient';

export function usePatterns() {
  return useQuery(['patterns'], fetchPatterns, {
    staleTime: 1000 * 10,
  });
}
