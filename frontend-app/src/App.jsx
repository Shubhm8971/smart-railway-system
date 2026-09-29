import { useEffect, useState } from "react";
import SeatSelection from "./components/SeatSelection";

const API = import.meta.env?.VITE_API_URL ?? "http://localhost:8000";
const DEMO_USER_ID = "64b7f0c2a1b2c3d4e5f60718";

export default function App() {
  const [trains, setTrains] = useState([]);
  const [trainId, setTrainId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [token, setToken] = useState(() => localStorage.getItem("smart-railway-token") || "");
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ name: "", email: "", password: "" });
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function loadTrains() {
      try {
        const response = await fetch(`${API}/trains`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Could not load trains (${response.status})`);

        const records = await response.json();
        setTrains(records);
        setTrainId((current) => current || records[0]?._id || "");
      } catch (loadError) {
        if (loadError.name !== "AbortError") {
          setError(loadError.message || "Could not connect to the railway API");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadTrains();
    return () => controller.abort();
  }, []);

  async function authenticate(event) {
    event.preventDefault();
    setAuthError("");
    const endpoint = authMode === "register" ? "register" : "login";
    const body = authMode === "register"
      ? authForm
      : { email: authForm.email, password: authForm.password };

    try {
      const response = await fetch(`${API}/users/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) {
        const detail = typeof result.detail === "string" ? result.detail : "Authentication failed";
        throw new Error(detail);
      }
      localStorage.setItem("smart-railway-token", result.access_token);
      setToken(result.access_token);
    } catch (authFailure) {
      setAuthError(authFailure.message || "Could not connect to the authentication API");
    }
  }

  function signOut() {
    localStorage.removeItem("smart-railway-token");
    setToken("");
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <main className="mx-auto max-w-3xl">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-sky-800">Smart Railway</p>
            <h1 className="text-2xl font-bold text-slate-950">Live train availability</h1>
          </div>
          {trains.length > 1 && (
            <label className="grid gap-1 text-sm font-medium text-slate-700">
              Select train
              <select
                className="rounded-md border border-slate-300 bg-white px-3 py-2"
                value={trainId}
                onChange={(event) => setTrainId(event.target.value)}
              >
                {trains.map((train) => (
                  <option key={train._id} value={train._id}>
                    {train.number} · {train.source} to {train.destination}
                  </option>
                ))}
              </select>
            </label>
          )}
        </header>

        {loading && <p className="text-slate-600">Connecting to the railway API…</p>}
        {!loading && error && <p className="text-red-700" role="alert">{error}</p>}
        {!loading && !error && trains.length === 0 && (
          <p className="text-slate-600">No trains are available from the API yet.</p>
        )}
        {!loading && !error && !token && (
          <form onSubmit={authenticate} className="mb-6 grid max-w-md gap-3 rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-semibold text-slate-900">
              {authMode === "register" ? "Create an account" : "Sign in"}
            </h2>
            {authMode === "register" && (
              <input
                required
                minLength={1}
                maxLength={100}
                autoComplete="name"
                placeholder="Name"
                value={authForm.name}
                onChange={(event) => setAuthForm({ ...authForm, name: event.target.value })}
                className="rounded-md border border-slate-300 px-3 py-2"
              />
            )}
            <input
              required
              type="email"
              autoComplete="email"
              placeholder="Email"
              value={authForm.email}
              onChange={(event) => setAuthForm({ ...authForm, email: event.target.value })}
              className="rounded-md border border-slate-300 px-3 py-2"
            />
            <input
              required
              minLength={8}
              type="password"
              autoComplete={authMode === "register" ? "new-password" : "current-password"}
              placeholder="Password"
              value={authForm.password}
              onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })}
              className="rounded-md border border-slate-300 px-3 py-2"
            />
            <button className="rounded-md bg-slate-900 px-4 py-2 font-medium text-white">
              {authMode === "register" ? "Register" : "Sign in"}
            </button>
            {authError && <p className="text-sm text-red-700" role="alert">{authError}</p>}
            <button
              type="button"
              className="justify-self-start text-sm font-medium text-sky-800 underline"
              onClick={() => {
                setAuthMode(authMode === "register" ? "login" : "register");
                setAuthError("");
              }}
            >
              {authMode === "register" ? "Already registered? Sign in" : "New here? Create an account"}
            </button>
          </form>
        )}
        {!loading && !error && token && (
          <div className="mb-4 flex justify-end">
            <button onClick={signOut} className="text-sm font-medium text-slate-700 underline">
              Sign out
            </button>
          </div>
        )}
        {!loading && !error && trainId && token && (
          <SeatSelection
            key={trainId}
            trainId={trainId}
            token={token}
            onUnauthorized={signOut}
          />
        )}
      </main>
    </div>
  );
}