// Local-first API export. Admin/public pages use localApi.
// Avoid hard dependency on Atoms SDK at module load for local runs.
export { client } from './localApi';
