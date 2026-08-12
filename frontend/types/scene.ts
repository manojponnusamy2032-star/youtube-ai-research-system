export interface Scene {
  scene_number: number;
  duration_seconds: number;
  visual: string;
  narration: string;
  dialogue: string;
  sfx: string;
}

export interface ScriptPlan {
  intro: string;
  sections: Array<Record<string, unknown>>;
  cta: string;
  estimated_duration_minutes: number;
  scenes: Scene[];
}