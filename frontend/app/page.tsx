import { redirect } from "next/navigation";

// The application shell (sidebar, navbar, auth guard) lives under /dashboard.
// The root route just forwards there; the dashboard layout will bounce
// unauthenticated visitors to /login.
export default function RootPage() {
  redirect("/dashboard");
}
