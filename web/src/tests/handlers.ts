import { http, HttpResponse } from "msw";
import rules from "./fixtures/rules.json";
import dataStatus from "./fixtures/data-status.json";
import generateResponse from "./fixtures/generate-response.json";

const API_URL = "http://localhost:8000";

export const handlers = [
  http.get(`${API_URL}/api/rules`, () => HttpResponse.json(rules)),
  http.get(`${API_URL}/api/data/status`, () => HttpResponse.json(dataStatus)),
  http.post(`${API_URL}/api/generate`, () => HttpResponse.json(generateResponse)),
];
