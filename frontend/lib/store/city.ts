import { create } from "zustand";
import { persist } from "zustand/middleware";

interface CityState {
  selectedCity: string;
  setCity: (city: string) => void;
}

export const useCityStore = create<CityState>()(
  persist(
    (set) => ({
      selectedCity: "Pune",
      setCity: (city) => set({ selectedCity: city }),
    }),
    { name: "city-store" }
  )
);

export const SUPPORTED_CITIES = ["Pune", "Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata"];
