"""Test script for Convex API client."""

import os
from convex_client import (
    list_sites, get_site, create_site, delete_site,
    list_docs, get_doc, save_doc, delete_doc, get_doc_by_url
)

# Set API URL
os.environ["CONVEX_API_URL"] = "https://tangentleman--convex-api-fastapi-app-dev.modal.run"

def test_sites():
    """Test site management functions."""
    print("=" * 60)
    print("Testing Sites Management")
    print("=" * 60)
    
    # List sites
    print("\n1. Listing all sites...")
    sites = list_sites()
    print(f"   Found {sites['total']} sites")
    
    # Create a test site
    print("\n2. Creating test site...")
    result = create_site(
        site_id="test-api-site",
        name="API Test Site",
        base_url="https://test.example.com",
        selector=".main-content",
        pages={"page1": "/page1", "page2": "/page2"},
        sections={"docs": "/docs"}
    )
    print(f"   Site created: {result['siteId']}")
    
    # Get the site
    print("\n3. Getting site details...")
    site = get_site("test-api-site")
    print(f"   Site: {site['name']}")
    print(f"   Pages: {list(site['pages'].keys())}")
    
    # List sites again
    print("\n4. Listing sites again...")
    sites = list_sites()
    print(f"   Found {sites['total']} sites")
    
    return "test-api-site"


def test_docs(site_id: str):
    """Test documentation management functions."""
    print("\n" + "=" * 60)
    print("Testing Docs Management")
    print("=" * 60)
    
    # List docs (should be empty)
    print("\n1. Listing docs (should be empty)...")
    docs = list_docs(site_id)
    print(f"   Found {docs['total']} docs")
    
    # Save a doc
    print("\n2. Saving a doc...")
    markdown_content = """# Page 1

This is the content for page 1.

## Section 1

Some content here.

## Section 2

More content.
"""
    result = save_doc(
        site_id=site_id,
        page="page1",
        url="https://test.example.com/page1",
        markdown=markdown_content
    )
    print(f"   Doc saved: {result['siteId']}/{result['page']}")
    print(f"   Content hash: {result['contentHash'][:16]}...")
    
    # List docs again
    print("\n3. Listing docs again...")
    docs = list_docs(site_id)
    print(f"   Found {docs['total']} docs")
    for doc in docs['docs']:
        print(f"   - {doc['page']}: {doc['url']}")
    
    # Get the doc
    print("\n4. Getting doc content...")
    doc = get_doc(site_id, "page1")
    print(f"   Page: {doc['page']}")
    print(f"   URL: {doc['url']}")
    print(f"   Content length: {len(doc['markdown'])} chars")
    print(f"   Preview: {doc['markdown'][:100]}...")
    
    # Get doc by URL
    print("\n5. Getting doc by URL...")
    doc_by_url = get_doc_by_url("https://test.example.com/page1")
    print(f"   Found doc: {doc_by_url['page']}")
    
    # Save another doc
    print("\n6. Saving another doc...")
    save_doc(
        site_id=site_id,
        page="page2",
        url="https://test.example.com/page2",
        markdown="# Page 2\n\nContent for page 2."
    )
    print("   Doc saved")
    
    # List docs
    print("\n7. Listing all docs...")
    docs = list_docs(site_id)
    print(f"   Found {docs['total']} docs")
    for doc in docs['docs']:
        print(f"   - {doc['page']}: {doc['url']}")


def test_full_lifecycle():
    """Test complete lifecycle: create site, add 3 pages, delete pages, delete site."""
    print("\n" + "=" * 60)
    print("Testing Full Lifecycle")
    print("=" * 60)
    
    site_id = "test-lifecycle-site"
    base_url = "https://test-lifecycle.example.com"
    
    # Step 1: Create test site with 3 pages
    print("\n1. Creating test site with 3 pages...")
    pages_config = {
        "intro": "/intro",
        "getting-started": "/getting-started",
        "advanced": "/advanced"
    }
    result = create_site(
        site_id=site_id,
        name="Lifecycle Test Site",
        base_url=base_url,
        selector=".content",
        pages=pages_config
    )
    print(f"   Site created: {result['siteId']}")
    
    # Step 2: Add markdown pages for all 3 pages
    print("\n2. Adding markdown content for 3 pages...")
    markdown_pages = {
        "intro": """# Introduction

Welcome to the introduction page.

This page covers the basics and provides an overview of the system.

## Key Features

- Feature 1
- Feature 2
- Feature 3
""",
        "getting-started": """# Getting Started

This guide will help you get started quickly.

## Installation

1. Step one
2. Step two
3. Step three

## Quick Start

Here's a quick example to get you started.
""",
        "advanced": """# Advanced Topics

For advanced users, here are some advanced topics.

## Advanced Configuration

Advanced configuration options are available.

## Performance Tuning

Tips for optimizing performance.
"""
    }
    
    saved_pages = []
    for page_name, markdown_content in markdown_pages.items():
        result = save_doc(
            site_id=site_id,
            page=page_name,
            url=f"{base_url}{pages_config[page_name]}",
            markdown=markdown_content
        )
        saved_pages.append(page_name)
        print(f"   Saved: {page_name} ({len(markdown_content)} chars)")
    
    # Verify all pages are saved
    print("\n3. Verifying all pages are saved...")
    docs = list_docs(site_id)
    print(f"   Found {docs['total']} docs")
    for doc in docs['docs']:
        print(f"   - {doc['page']}: {doc['url']}")
    
    # Step 3: Delete all pages
    print("\n4. Deleting all pages...")
    for page_name in saved_pages:
        try:
            delete_doc(site_id, page_name)
            print(f"   Deleted: {page_name}")
        except Exception as e:
            print(f"   Error deleting {page_name}: {e}")
    
    # Verify all pages are deleted
    print("\n5. Verifying all pages are deleted...")
    docs = list_docs(site_id)
    print(f"   Found {docs['total']} docs (should be 0)")
    
    # Step 4: Delete the site
    print("\n6. Deleting the site...")
    try:
        delete_site(site_id)
        print(f"   Deleted site: {site_id}")
    except Exception as e:
        print(f"   Error deleting site: {e}")
    
    # Verify site is deleted
    print("\n7. Verifying site is deleted...")
    try:
        get_site(site_id)
        print(f"   WARNING: Site {site_id} still exists!")
    except Exception as e:
        print(f"   Site successfully deleted (expected error: {type(e).__name__})")
    
    print("\n" + "=" * 60)
    print("Full lifecycle test completed!")
    print("=" * 60)


def cleanup(site_id: str):
    """Clean up test data - delete all docs and the site."""
    print("\n" + "=" * 60)
    print("Cleanup")
    print("=" * 60)
    
    # Delete all docs for the site
    print("\n1. Deleting all docs...")
    try:
        docs = list_docs(site_id)
        deleted_count = 0
        for doc in docs.get('docs', []):
            try:
                delete_doc(site_id, doc['page'])
                print(f"   Deleted: {doc['page']}")
                deleted_count += 1
            except Exception as e:
                print(f"   Error deleting {doc['page']}: {e}")
        print(f"   Deleted {deleted_count} docs")
    except Exception as e:
        print(f"   Error listing docs: {e}")
    
    # Delete site
    print("\n2. Deleting test site...")
    try:
        delete_site(site_id)
        print(f"   Deleted site: {site_id}")
    except Exception as e:
        print(f"   Error deleting site: {e}")


if __name__ == "__main__":
    import sys
    
    # If --lifecycle flag is passed, run only the lifecycle test
    if "--lifecycle" in sys.argv:
        try:
            test_full_lifecycle()
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
    else:
        try:
            site_id = test_sites()
            test_docs(site_id)
            
            # Clean up test data
            cleanup(site_id)
            
            print("\n" + "=" * 60)
            print("All tests completed!")
            print("=" * 60)
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()

