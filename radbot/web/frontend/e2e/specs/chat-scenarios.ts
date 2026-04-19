/**
 * Per-scenario rubrics consumed by chat.spec.ts. Each scenario sends a prompt,
 * waits for beto's response, and grades it via the LLM judge against `expect`.
 *
 * Add a new scenario by appending to this array. Keep `expect` as a clear
 * description of what beto SHOULD do — vague rubrics produce vague verdicts.
 *
 * The judge is told to set `category: "wrong_agent"` for unintended sub-agent
 * transfers and `category: "refusal"` for unjustified can't-do responses, so
 * the rubric can be terse — list the negative cases too.
 */
export interface ChatScenario {
  name: string;
  prompt: string;
  expect: string;
  timeoutMs?: number;
}

export const chatScenarios: ChatScenario[] = [
  {
    name: "time-question",
    prompt: "what time is it in San Francisco right now?",
    expect:
      "Beto should report a current time for San Francisco (PST/PDT). May call get_current_time tool. " +
      "Should NOT refuse, NOT say it has no access to time, NOT transfer to a sub-agent for this trivia.",
    timeoutMs: 30_000,
  },
  {
    name: "identity-check",
    prompt: "who are you and what can you help me with?",
    expect:
      "Beto should introduce itself with its 90s SoCal persona (radical/gnarly/totally vibe is a tell, not required) " +
      "and mention orchestrating sub-agents OR list capability domains (calendar, home, code, research, etc.). " +
      "Should NOT respond as a generic assistant with no personality.",
    timeoutMs: 20_000,
  },
  {
    name: "math-trivia",
    prompt: "what is 17 times 23?",
    expect:
      "Beto should compute or state the answer 391. May use code execution sub-agent. " +
      "Wrong number is a hallucination; refusing to do arithmetic is wrong_agent or refusal.",
    timeoutMs: 30_000,
  },
];
