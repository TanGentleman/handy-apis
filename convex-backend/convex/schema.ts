import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // sites - documentation site configurations
  sites: defineTable({
    siteId: v.string(),
    name: v.string(),
    baseUrl: v.string(),
    selector: v.string(),
    method: v.string(),
    pages: v.any(), // dict of page_name -> path
    sections: v.optional(v.any()), // dict of section_name -> path
  }).index("by_site_id", ["siteId"]),
  // docs - documentation links
  docs: defineTable({
    siteId: v.string(),
    page: v.string(),
    url: v.string(),
    markdown: v.string(),
    updatedAt: v.number(),
    contentHash: v.string(),
  })
    .index("by_url", ["url"])
    .index("by_site", ["siteId"])
    .index("by_site_and_page", ["siteId", "page"]),
});