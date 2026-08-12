"use client";
import React, { useState } from 'react';
import ResearchForm from '../../components/research/ResearchForm';
import WorkflowProgress from '../../components/research/WorkflowProgress';
import { useCreateResearch, useWorkflows, useWorkflow } from '../../hooks/useResearch';
import Loading from '../../components/ui/Loading';

export default function ResearchPage() {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const { data: workflows, isLoading: workflowsLoading, error: workflowsError } = useWorkflows(50);
  const create = useCreateResearch();
  const { data: selectedWorkflow, isLoading: selectedLoading, error: selectedError } = useWorkflow(selectedWorkflowId || undefined);

  const workflowsHasError = Boolean(workflowsError);
  const selectedHasError = Boolean(selectedError);

  const onCreate = (payload: any) => {
    // Normalize payload to backend expected shape in case the form uses legacy keys like `topic` or camelCase
    const body: any = {};
    body.keyword = payload.keyword ?? payload.topic ?? payload.query ?? payload.q;
    body.max_results = payload.max_results ?? payload.maxResults ?? payload.limit ?? 50;
    body.limit = payload.limit ?? payload.max_results ?? payload.maxResults ?? 50;
    body.run_title_generation = payload.run_title_generation ?? payload.runTitleGeneration ?? false;
    body.run_content_generation = payload.run_content_generation ?? payload.runContentGeneration ?? false;
    create.mutate(body);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Research</h1>
        <p className="text-sm text-slate-500">Start new research workflows</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 p-4 rounded shadow bg-white dark:bg-slate-800">
          <h3 className="font-semibold mb-2">Start Research</h3>
          <ResearchForm onSubmit={onCreate} />
          {create.isLoading && <div className="mt-2 text-sm text-slate-500">Starting workflow...</div>}
          {create.isError && <div className="mt-2 text-sm text-red-600">Failed to start workflow</div>}
        </div>

        <div className="lg:col-span-2">
          <div className="p-4 rounded shadow bg-white dark:bg-slate-800 mb-6">
            <h3 className="font-semibold mb-2">Workflows</h3>
            {workflowsLoading && <Loading />}
            {workflowsHasError && <div className="text-red-600">Failed to load workflows</div>}
            {!workflowsLoading && !workflowsHasError && (
              <ul className="space-y-2">
                {workflows?.map((w: any) => (
                  <li key={w.id} className="p-2 border rounded flex items-center justify-between">
                    <div>
                      <div className="font-medium">{w.topic || w.payload?.topic || 'Untitled'}</div>
                      <div className="text-xs text-slate-500">{w.status} • {new Date(w.created_at).toLocaleString()}</div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div style={{ width: 160 }}>
                        <WorkflowProgress percent={w.progress_percentage ?? 0} />
                      </div>
                      <button className="px-3 py-1 border rounded" onClick={() => setSelectedWorkflowId(w.id)}>View</button>
                    </div>
                  </li>
                ))}
                {workflows?.length === 0 && <li className="text-sm text-slate-500">No workflows</li>}
              </ul>
            )}
          </div>

          <div className="p-4 rounded shadow bg-white dark:bg-slate-800">
            <h3 className="font-semibold mb-2">Workflow Status</h3>
            {selectedWorkflowId === null && <div className="text-sm text-slate-500">Select a workflow to view details</div>}
            {selectedLoading && <Loading />}
            {selectedHasError && <div className="text-red-600">Failed to load workflow details</div>}
            {selectedWorkflow && (
              <div>
                <div className="mb-2 font-medium">{selectedWorkflow.topic || selectedWorkflow.payload?.topic}</div>
                <div className="text-sm text-slate-500 mb-2">Status: {selectedWorkflow.status}</div>
                <div className="mb-2">
                  <WorkflowProgress percent={selectedWorkflow.progress_percentage ?? 0} />
                </div>
                <div className="text-sm text-slate-500">Started: {new Date(selectedWorkflow.started_at || selectedWorkflow.created_at).toLocaleString()}</div>
                <div className="text-sm text-slate-500">Processed: {selectedWorkflow.processed_videos ?? 0}</div>
                <div className="text-sm text-slate-500">Failed: {selectedWorkflow.failed_videos ?? 0}</div>
                {selectedWorkflow.error_text && <div className="text-sm text-red-600 mt-2">Error: {selectedWorkflow.error_text}</div>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
