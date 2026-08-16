import "dotenv/config";
import { defineConfig, env } from "prisma/config";

export default defineConfig({
  earlyAccess: true,
  schema: "schema.prisma",
  migrate: {
    async url() {
      return env("DIRECT_URL");
    },
  },
});
