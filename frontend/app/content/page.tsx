"use client";

import { FormEvent, useState } from 'react';
import { useContentGeneration } from '../../hooks/useContent';
import Loading from '../../components/ui/Loading';

export default function ContentPage() {
  const [topic, setTopic] = useState('');
  const [niche, setNiche] = useState('YouTube');
  const [audience, setAudience] = useState('creators');
  const [copied, setCopied] = useState(false);

  const { mutate, data, error, isLoading, isError, isSuccess } = useContentGeneration();

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!topic.trim()) return;
    mutate({ topic: topic.trim(), niche: niche.trim() || 'YouTube', audience: audience.trim() || 'creators' });
  };

  const packageData = data?.content_package;

  const exportScript = () => {
    if (!packageData?.script?.scenes) return;
    const blob = new Blob([JSON.stringify(packageData.script, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'viral-script.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const copyScript = async () => {
    if (!packageData?.script?.scenes) return;
    
    // Convert script scenes to readable text
    const scriptText = packageData.script.scenes
      .map((scene: any, index: number) => {
        const lines = [`Scene ${index + 1}:`];
        if (scene.title) lines.push(`Title: ${scene.title}`);
        if (scene.duration) lines.push(`Duration: ${scene.duration}`);
        if (scene.visual) lines.push(`Visual: ${scene.visual}`);
        if (scene.dialogue || scene.content) lines.push(`Content: ${scene.dialogue || scene.content}`);
        if (scene.narration) lines.push(`Narration: ${scene.narration}`);
        return lines.join('\n');
      })
      .join('\n\n');

    try {
      await navigator.clipboard.writeText(scriptText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy script:', err);
    }
  };

  const hasScenes = Boolean(packageData?.script?.scenes?.length);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Content Generator</h1>
        <p className="mt-2 text-slate-500">Generate a complete content package from a topic, niche, and audience.</p>
      </div>

      <form onSubmit={onSubmit} className="grid gap-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-950">
        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Topic</span>
            <input
              type="text"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="Enter your video topic"
              className="w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:bg-white focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:bg-slate-900 dark:focus:ring-slate-800"
              required
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Niche</span>
            <input
              type="text"
              value={niche}
              onChange={(event) => setNiche(event.target.value)}
              placeholder="E.g. creator economy, education, gaming"
              className="w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:bg-white focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:bg-slate-900 dark:focus:ring-slate-800"
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Audience</span>
            <input
              type="text"
              value={audience}
              onChange={(event) => setAudience(event.target.value)}
              placeholder="E.g. new creators, small businesses"
              className="w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:bg-white focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:bg-slate-900 dark:focus:ring-slate-800"
            />
          </label>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1 text-sm text-slate-500 dark:text-slate-400">
            <p className="font-medium text-slate-700 dark:text-slate-200">Complete content package</p>
            <p>Submit to generate titles, hook, script, thumbnail concept, and SEO metadata.</p>
          </div>
          <button
            type="submit"
            className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isLoading}
          >
            Generate Content
          </button>
        </div>
      </form>

      {isLoading && <Loading />}

      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          <strong className="font-semibold">Generation failed.</strong>
          <p className="mt-1 text-sm">{error instanceof Error ? error.message : 'Unable to generate content package.'}</p>
        </div>
      )}

      {isSuccess && packageData && (
        <div className="space-y-6">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Generated Package</h2>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              {packageData.title && (
                <div className="rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                  <p className="text-sm font-medium text-slate-500">Best Title</p>
                  <p className="mt-2 text-base font-semibold text-slate-900 dark:text-white">{packageData.title}</p>
                </div>
              )}

              {packageData.hook && (
                <div className="rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                  <p className="text-sm font-medium text-slate-500">Hook</p>
                  <p className="mt-2 text-base text-slate-900 dark:text-white">{packageData.hook?.script ?? packageData.hook}</p>
                </div>
              )}
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              {packageData.thumbnail && (
                <div className="rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                  <p className="text-sm font-medium text-slate-500">Thumbnail Concept</p>
                  <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-900 dark:text-slate-100">{JSON.stringify(packageData.thumbnail, null, 2)}</pre>
                </div>
              )}

              {packageData.seo && (
                <div className="rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                  <p className="text-sm font-medium text-slate-500">SEO Metadata</p>
                  <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-900 dark:text-slate-100">{JSON.stringify(packageData.seo, null, 2)}</pre>
                </div>
              )}
            </div>

            {packageData.script && (
              <div className="mt-4 rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-slate-500">Script Plan</p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={copyScript}
                      disabled={!hasScenes}
                      className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {copied ? 'Copied!' : hasScenes ? 'Copy Script' : 'No script available'}
                    </button>
                    <button
                      type="button"
                      onClick={exportScript}
                      disabled={!hasScenes}
                      className="inline-flex items-center justify-center rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {hasScenes ? 'Export Script' : 'No script available'}
                    </button>
                  </div>
                </div>
                <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-900 dark:text-slate-100">{JSON.stringify(packageData.script, null, 2)}</pre>
              </div>
            )}

            {packageData.video_production_plan && (
              <div className="mt-4 rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                <p className="text-sm font-medium text-slate-500">Video Production Plan</p>
                <div className="mt-2 grid gap-4 lg:grid-cols-3">
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Title</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.video_production_plan.title}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Total Duration</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.video_production_plan.total_duration_seconds}s</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Scene Count</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.video_production_plan.scenes?.length ?? 0}</p>
                  </div>
                </div>
                <div className="mt-4 space-y-3">
                  {(packageData.video_production_plan.scenes || []).map((scene: any, index: number) => (
                    <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white">Scene {scene.scene_number}</p>
                        <p className="text-xs text-slate-500">{scene.duration_seconds}s</p>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-medium text-slate-500">Visual</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{scene.visual_description}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Narration</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{scene.narration}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Dialogue</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{scene.dialogue || '—'}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Sound Effects</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{scene.sound_effects || '—'}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Camera Direction</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{scene.camera_direction}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Animation Direction</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{scene.animation_direction}</p>
                        </div>
                      </div>
                      <div className="mt-3">
                        <p className="text-xs font-medium text-slate-500">Transition</p>
                        <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{scene.transition}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {packageData.scene_asset_plan && (
              <div className="mt-4 rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                <p className="text-sm font-medium text-slate-500">Scene Assets</p>
                <div className="mt-2 grid gap-4 lg:grid-cols-3">
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Total Assets</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.scene_asset_plan.total_assets}</p>
                  </div>
                </div>
                <div className="mt-4 space-y-3">
                  {(packageData.scene_asset_plan.assets || []).map((asset: any, index: number) => (
                    <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white">Scene {asset.scene_number}</p>
                        <p className="text-xs text-slate-500">{asset.asset_type}</p>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-medium text-slate-500">Character</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{asset.character || '—'}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Action</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{asset.action}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Description</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{asset.description}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Position</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{asset.position}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Expression</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{asset.expression}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Duration</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{asset.duration_seconds}s</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {packageData.visual_style_plan && (
              <div className="mt-4 rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                <p className="text-sm font-medium text-slate-500">Visual Style Plan</p>
                <div className="mt-2 grid gap-4 lg:grid-cols-3">
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Style</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.visual_style_plan.style_name}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Art Style</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.visual_style_plan.art_style}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Background Style</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.visual_style_plan.background_style}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Lighting</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.visual_style_plan.lighting_style}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Camera Style</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.visual_style_plan.camera_style}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Characters</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.visual_style_plan.characters?.length ?? 0}</p>
                  </div>
                </div>
                <div className="mt-4 space-y-3">
                  {(packageData.visual_style_plan.characters || []).map((character: any, index: number) => (
                    <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                      <p className="text-sm font-semibold text-slate-900 dark:text-white">{character.name}</p>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-medium text-slate-500">Role</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{character.role}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Visual Style</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{character.visual_style}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Default Expression</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{character.default_expression}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Color</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{character.color}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Clothing</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{character.clothing}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Consistency Notes</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{character.consistency_notes}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                  <p className="text-sm font-semibold text-slate-900 dark:text-white">Consistency Rules</p>
                  <ul className="mt-2 list-inside list-disc space-y-1">
                    {(packageData.visual_style_plan.consistency_rules || []).map((rule: string, index: number) => (
                      <li key={index} className="text-sm text-slate-900 dark:text-slate-100">{rule}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {packageData.character_asset_plan && (
              <div className="mt-4 rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                <p className="text-sm font-medium text-slate-500">Character Assets</p>
                <div className="mt-4 space-y-3">
                  {(packageData.character_asset_plan.characters || []).map((char: any, index: number) => (
                    <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white">{char.name}</p>
                        <p className="text-xs text-slate-500">{char.character_id}</p>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-medium text-slate-500">Body Style</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{char.body_style}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Face Style</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{char.face_style}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Clothing</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{char.clothing}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Colors</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{char.primary_color} / {char.secondary_color}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Reference Prompt</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{char.reference_prompt}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Consistency Rules</p>
                          <ul className="mt-1 list-inside list-disc space-y-1">
                            {(char.consistency_rules || []).map((rule: string, ruleIndex: number) => (
                              <li key={ruleIndex} className="text-sm text-slate-900 dark:text-slate-100">{rule}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                  <p className="text-sm font-semibold text-slate-900 dark:text-white">Global Character Rules</p>
                  <ul className="mt-2 list-inside list-disc space-y-1">
                    {(packageData.character_asset_plan.global_character_rules || []).map((rule: string, index: number) => (
                      <li key={index} className="text-sm text-slate-900 dark:text-slate-100">{rule}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {packageData.render_job_plan && (
              <div className="mt-4 rounded-3xl bg-slate-50 p-4 dark:bg-slate-950">
                <p className="text-sm font-medium text-slate-500">Render Jobs</p>
                <div className="mt-2 grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Total Jobs</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.render_job_plan.total_jobs}</p>
                  </div>
                  <div className="rounded-2xl bg-white p-4 dark:bg-slate-900">
                    <p className="text-xs font-medium text-slate-500">Total Duration</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">{packageData.render_job_plan.total_duration_seconds}s</p>
                  </div>
                </div>
                <div className="mt-4 space-y-3">
                  {(packageData.render_job_plan.jobs || []).map((job: any, index: number) => (
                    <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white">Scene {job.scene_number}</p>
                        <p className="text-xs text-slate-500">{job.render_type}</p>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div>
                          <p className="text-xs font-medium text-slate-500">Duration</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{job.duration_seconds}s</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Character IDs</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{(job.character_ids || []).join(", ") || "—"}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500">Asset IDs</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{(job.asset_ids || []).join(", ") || "—"}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Visual Prompt</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{job.visual_prompt}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Animation Instructions</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{job.animation_instructions}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Camera Instructions</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{job.camera_instructions}</p>
                        </div>
                        <div className="md:col-span-2">
                          <p className="text-xs font-medium text-slate-500">Audio Requirements</p>
                          <p className="mt-1 text-sm text-slate-900 dark:text-slate-100">{job.audio_requirements}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
