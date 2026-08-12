"use client";
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createResearch, listWorkflows, getWorkflow } from '../services/researchClient';

export function useCreateResearch() {
  const qc = useQueryClient();
  return useMutation((payload: any) => createResearch(payload), {
    onSuccess: () => qc.invalidateQueries(['recent-workflows']),
  });
}

export function useWorkflows(limit = 50) {
  return useQuery(['recent-workflows', limit], () => listWorkflows(limit), { staleTime: 1000 * 10 });
}

export function useWorkflow(id?: string) {
  return useQuery(['workflow', id], () => (id ? getWorkflow(id) : Promise.resolve(null)), { enabled: !!id, staleTime: 1000 * 5 });
}
