import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDarkMode } from "./useDarkMode";

describe("useDarkMode", () => {
  beforeEach(() => {
    localStorage.clear();
    // Reset the class list on the html element before each test.
    document.documentElement.classList.remove("dark");
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("defaults to dark when localStorage is empty", () => {
    const { result } = renderHook(() => useDarkMode());
    const [isDark] = result.current;
    expect(isDark).toBe(true);
  });

  it("applies the dark class to documentElement when defaulting to dark", () => {
    renderHook(() => useDarkMode());
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("reads stored 'dark' preference from localStorage", () => {
    localStorage.setItem("theme", "dark");
    const { result } = renderHook(() => useDarkMode());
    const [isDark] = result.current;
    expect(isDark).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("reads stored 'light' preference from localStorage", () => {
    localStorage.setItem("theme", "light");
    const { result } = renderHook(() => useDarkMode());
    const [isDark] = result.current;
    expect(isDark).toBe(false);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("toggles from dark to light and persists to localStorage", () => {
    const { result } = renderHook(() => useDarkMode());

    // starts dark
    expect(result.current[0]).toBe(true);

    act(() => {
      result.current[1](); // toggleDark
    });

    expect(result.current[0]).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("toggles from light to dark and persists to localStorage", () => {
    localStorage.setItem("theme", "light");
    const { result } = renderHook(() => useDarkMode());

    // starts light
    expect(result.current[0]).toBe(false);

    act(() => {
      result.current[1](); // toggleDark
    });

    expect(result.current[0]).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("removes the dark class when toggling to light", () => {
    const { result } = renderHook(() => useDarkMode());
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    act(() => {
      result.current[1]();
    });

    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("persists 'dark' to localStorage on mount when defaulting to dark", () => {
    renderHook(() => useDarkMode());
    expect(localStorage.getItem("theme")).toBe("dark");
  });
});
