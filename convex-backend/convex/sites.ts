import { query, mutation } from "./_generated/server";
import { v } from "convex/values";

// Query: List all sites
export const list = query({
  handler: async (ctx) => {
    const sites = await ctx.db.query("sites").collect();
    return sites.map(site => ({
      id: site._id,
      siteId: site.siteId,
      name: site.name,
      baseUrl: site.baseUrl,
      selector: site.selector,
      method: site.method,
      pages: site.pages,
      sections: site.sections,
      createdAt: site._creationTime,
    }));
  },
});

// Query: Get a specific site by siteId
export const get = query({
  args: { siteId: v.string() },
  handler: async (ctx, args) => {
    const site = await ctx.db
      .query("sites")
      .withIndex("by_site_id", (q) => q.eq("siteId", args.siteId))
      .first();

    if (!site) {
      return null;
    }

    return {
      id: site._id,
      siteId: site.siteId,
      name: site.name,
      baseUrl: site.baseUrl,
      selector: site.selector,
      method: site.method,
      pages: site.pages,
      sections: site.sections,
      createdAt: site._creationTime,
    };
  },
});

// Mutation: Add or update a site
export const upsert = mutation({
  args: {
    siteId: v.string(),
    name: v.string(),
    baseUrl: v.string(),
    selector: v.string(),
    method: v.string(),
    pages: v.any(),
    sections: v.optional(v.any()),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query("sites")
      .withIndex("by_site_id", (q) => q.eq("siteId", args.siteId))
      .first();

    if (existing) {
      await ctx.db.patch(existing._id, {
        name: args.name,
        baseUrl: args.baseUrl,
        selector: args.selector,
        method: args.method,
        pages: args.pages,
        sections: args.sections,
      });
      return { id: existing._id, updated: true };
    } else {
      const id = await ctx.db.insert("sites", {
        siteId: args.siteId,
        name: args.name,
        baseUrl: args.baseUrl,
        selector: args.selector,
        method: args.method,
        pages: args.pages,
        sections: args.sections,
      });
      return { id, updated: false };
    }
  },
});

// Mutation: Delete a site
export const remove = mutation({
  args: { siteId: v.string() },
  handler: async (ctx, args) => {
    const site = await ctx.db
      .query("sites")
      .withIndex("by_site_id", (q) => q.eq("siteId", args.siteId))
      .first();

    if (site) {
      await ctx.db.delete(site._id);
      return { deleted: true };
    }
    return { deleted: false };
  },
});
