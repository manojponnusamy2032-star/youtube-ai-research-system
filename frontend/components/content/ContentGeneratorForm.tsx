"use client";
import { useForm } from 'react-hook-form';

export default function ContentGeneratorForm() {
  const { register, handleSubmit } = useForm<{ topic: string }>();
  const onSubmit = (v: { topic: string }) => console.log(v);
  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
      <div>
        <label className="block text-sm">Topic</label>
        <input {...register('topic')} className="mt-1 w-full border rounded p-2" />
      </div>
      <div>
        <button className="px-4 py-2 bg-slate-900 text-white rounded">Generate</button>
      </div>
    </form>
  );
}
