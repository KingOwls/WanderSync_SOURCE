const GRAPHQL_URL = import.meta.env.VITE_GRAPHQL_URL || 'http://localhost:8000/graphql';

export async function gql(query, variables = {}) {
  const response = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ query, variables }),
  });
  const payload = await response.json();
  if (!response.ok || payload.errors?.length) {
    const error = new Error(payload.errors?.[0]?.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.details = payload.errors;
    throw error;
  }
  return payload.data;
}
