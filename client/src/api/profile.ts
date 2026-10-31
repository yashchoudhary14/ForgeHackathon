import { post, request } from "./client";
import type { ProfileOut } from "./types";

export type UiMode = "talk" | "manual";

/** Saves the chosen mode on the profile (PUT /api/profile/{id} {mode}); creates an empty profile first if needed. */
export async function saveMode(
  profileId: string,
  mode: UiMode,
  language: string,
): Promise<string> {
  let profile: ProfileOut | null = null;
  if (profileId) {
    try {
      profile = await request<ProfileOut>(
        `/profile/${encodeURIComponent(profileId)}`,
      );
    } catch {
      profile = null;
    }
  }
  if (!profile)
    profile = await post<ProfileOut>("/profile", {
      data: {},
      sensitive: {},
      language,
    });
  await request<ProfileOut>(`/profile/${encodeURIComponent(profile.id)}`, {
    method: "PUT",
    body: JSON.stringify({
      data: profile.data,
      sensitive: profile.sensitive,
      language: profile.language,
      mode,
    }),
  });
  return profile.id;
}
