import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

// Query: List all docs for a site
export const listBySite = query({
  args: { siteId: v.string() },
  handler: async (ctx, args) => {
    const docs = await ctx.db
      .query("docs")
      .withIndex("by_site", (q) => q.eq("siteId", args.siteId))
      .collect();

    return docs.map(doc => ({
      id: doc._id,
      siteId: doc.siteId,
      page: doc.page,
      url: doc.url,
      contentHash: doc.contentHash,
      createdAt: doc._creationTime,
      updatedAt: doc.updatedAt,
      contentLength: doc.markdown.length,
    }));
  },
});

// Query: Get a specific doc by siteId and page
export const get = query({
  args: {
    siteId: v.string(),
    page: v.string(),
  },
  handler: async (ctx, args) => {
    const doc = await ctx.db
      .query("docs")
      .withIndex("by_site_and_page", (q) =>
        q.eq("siteId", args.siteId).eq("page", args.page)
      )
      .first();

    if (!doc) {
      return null;
    }

    return {
      id: doc._id,
      siteId: doc.siteId,
      page: doc.page,
      url: doc.url,
      markdown: doc.markdown,
      contentHash: doc.contentHash,
      createdAt: doc._creationTime,
      updatedAt: doc.updatedAt,
    };
  },
});

// Query: Get a doc by URL
export const getByUrl = query({
  args: { url: v.string() },
  handler: async (ctx, args) => {
    const doc = await ctx.db
      .query("docs")
      .withIndex("by_url", (q) => q.eq("url", args.url))
      .first();

    if (!doc) {
      return null;
    }

    return {
      id: doc._id,
      siteId: doc.siteId,
      page: doc.page,
      url: doc.url,
      markdown: doc.markdown,
      contentHash: doc.contentHash,
      createdAt: doc._creationTime,
      updatedAt: doc.updatedAt,
    };
  },
});

// Mutation: Add or update a doc
export const upsert = mutation({
  args: {
    siteId: v.string(),
    page: v.string(),
    url: v.string(),
    markdown: v.string(),
    contentHash: v.string(),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("docs")
      .withIndex("by_site_and_page", (q) =>
        q.eq("siteId", args.siteId).eq("page", args.page)
      )
      .first();

    const now = Date.now();

    if (existing) {
      await ctx.db.patch(existing._id, {
        url: args.url,
        markdown: args.markdown,
        contentHash: args.contentHash,
        updatedAt: now,
      });
      return { id: existing._id, updated: true, updatedAt: now };
    } else {
      const id = await ctx.db.insert("docs", {
        siteId: args.siteId,
        page: args.page,
        url: args.url,
        markdown: args.markdown,
        contentHash: args.contentHash,
        updatedAt: now,
      });
      return { id, updated: false, updatedAt: now };
    }
  },
});

// Mutation: Delete a doc
export const remove = mutation({
  args: {
    siteId: v.string(),
    page: v.string(),
  },
  handler: async (ctx, args) => {
    const doc = await ctx.db
      .query("docs")
      .withIndex("by_site_and_page", (q) =>
        q.eq("siteId", args.siteId).eq("page", args.page)
      )
      .first();

    if (doc) {
      await ctx.db.delete(doc._id);
      return { deleted: true };
    }
    return { deleted: false };
  },
});

// Query: Get all unique site IDs from docs
export const listSiteIds = query({
  handler: async (ctx) => {
    const docs = await ctx.db.query("docs").collect();
    const siteIds = [...new Set(docs.map(doc => doc.siteId))];
    return siteIds;
  },
});
