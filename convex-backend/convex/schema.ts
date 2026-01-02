import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // jobs - scrape jobs
  jobs: defineTable({
    url: v.string(),
    status: v.union(v.literal("pending"), v.literal("completed"), v.literal("failed")),
    isNew: v.boolean(),
    metadata: v.any(),
  }),
  // docs - documentation links
  docs: defineTable({
    url: v.string(),
    markdown: v.string(),
    updatedAt: v.number(),
    contentHash: v.string(),
  }).index("by_url", ["url"]),
});