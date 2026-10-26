/** DOM assertions shared by component tests; cleanup prevents cross-test UI leakage. */
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
afterEach(() => cleanup());
