import { create } from "zustand";
import { persist } from "zustand/middleware";

export const DEFAULT_CITY = "Pune";

export const SUPPORTED_CITIES = [
  "Pune",
  "Mumbai",
  "Delhi",
  "Bengaluru",
  "Chennai",
  "Kolkata",
] as const;

type SupportedCity = (typeof SUPPORTED_CITIES)[number];

interface CityState {
  selectedCity: string;
  setCity: (city: string) => void;
}

export const useCityStore = create<CityState>()(
  persist(
    (set) => ({
      selectedCity: DEFAULT_CITY,
      setCity: (city) => {
        const normalized = city.trim();
        if (!SUPPORTED_CITIES.includes(normalized as SupportedCity)) return;
        set({ selectedCity: normalized });
      },
    }),
    {
      name: "city-store",
      version: 1,
      migrate: () => ({ selectedCity: DEFAULT_CITY }),
    },
  ),
);
