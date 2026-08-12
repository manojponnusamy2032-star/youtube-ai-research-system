"use client";
/* eslint-disable no-unused-vars */
import { useForm } from 'react-hook-form';

type Form = { topic: string; audience?: string; niche?: string };

type Props = {
  onSubmit?: (payload: Form) => void;
  defaultValues?: Partial<Form>;
};

export default function ResearchForm({ onSubmit, defaultValues }: Props) {
  const { register, handleSubmit } = useForm<Form>({ defaultValues: defaultValues as any });
  const _onSubmit = (formData: Form) => {
    if (onSubmit) return onSubmit(formData);
    console.log('submit', formData);
  };
  return (
    <form onSubmit={handleSubmit(_onSubmit)} className="space-y-3">
      <div>
        <label className="block text-sm">Topic</label>
        <input {...register('topic', { required: true })} className="mt-1 w-full border rounded p-2" />
      </div>
      <div className="flex gap-2">
        <button type="submit" className="px-4 py-2 bg-slate-900 text-white rounded">Start</button>
      </div>
    </form>
  );
}
