# Trace Explorer

[Docs](https://docs.datadoghq.com/)&nbsp;>&nbsp;
[APM](https://docs.datadoghq.com/tracing/)&nbsp;>&nbsp;
[Trace Explorer](https://docs.datadoghq.com/tracing/trace_explorer/)[](https://datadog-docs.imgix.net/images/tracing/apm_lifecycle/trace_explorer.8473b57372bdbec2d23c381b0c32353b.png?fit=max&auto=format)
## [Overview](#overview)

The [Trace Explorer](https://app.datadoghq.com/apm/traces) gives you the ability to search all ingested or indexed spans using any tag on any span. The spans found by your query change depending on whether you are searching Live (all spans ingested in the last 15 minutes, rolling) or indexed spans (spans retained for 15 days by your custom filters).

Instrumented applications send traces to Datadog based on your configured [ingestion controls](https://docs.datadoghq.com/tracing/trace_pipeline/ingestion_controls). Ingested traces are available as Live traces for a rolling window of 15 minutes.

The Trace Explorer shows a **Live Search - All ingested data** indicator whenever you are in Live mode:

[](https://datadog-docs.imgix.net/images/tracing/trace_explorer/live_search.46b094fac64141731afb2d40b64377ce.png?fit=max&auto=format)All ingested traces are then passed through:

- [Custom retention filters](https://docs.datadoghq.com/tracing/trace_pipeline/trace_retention/#retention-filters) that you can create to determine which spans to index. Once indexed through a custom retention filter, traces are retained for **15 days**.
- The default [intelligent retention filter](https://docs.datadoghq.com/tracing/trace_pipeline/trace_retention/#datadog-intelligent-retention-filter) that retains a diverse set of traces. When indexed through the intelligent retention filter, traces are retained for **30 days**.

The Trace Explorer shows an **Search - Only Indexed Data** indicator whenever you search [indexed spans](https://docs.datadoghq.com/tracing/glossary/#indexed-span):

[](https://datadog-docs.imgix.net/images/tracing/trace_explorer/historical_search.6b86536a7e2c5a9ea6cded31737ec6bf.png?fit=max&auto=format)Live Search is the default view on the Traces page. Switch from Live Search to Indexed Data Search by using the time selector in the top right-hand corner.

### [Trace volume control](#trace-volume-control)

You can customize settings for both [ingestion and retention](https://docs.datadoghq.com/tracing/trace_pipeline/) to send and keep exactly what data is most relevant to you.

#### [Ingestion](#ingestion)

Control your volume globally with [Datadog Agent configuration options](https://docs.datadoghq.com/tracing/trace_pipeline/ingestion_mechanisms/#in-the-agent) or set precise [ingestion rules](https://docs.datadoghq.com/tracing/trace_pipeline/ingestion_mechanisms/#in-tracing-libraries-user-defined-rules) per service instrumented with Datadog APM.

#### [Indexing](#indexing)

After you instrument your services and ingest traces, set tag-based [retention filters](https://docs.datadoghq.com/tracing/trace_pipeline/trace_retention/#retention-filters) within the Datadog app so that Datadog retains spans that are relevant to you.

**Note:** Both ingested and indexed spans may impact your bill. For more information, see [APM Billing](https://docs.datadoghq.com/account_management/billing/apm_distributed_tracing/).

## [Live Search for 15 minutes](#live-search-for-15-minutes)

[](https://datadog-docs.imgix.net/images/tracing/apm_lifecycle/trace_explorer_live_search.934eedb136f51fbcb9cb76f8637fb2dc.png?fit=max&auto=format)When you use Live Search, Datadog displays spans as soon as they are sent by the Datadog Agent and before they have been indexed by your retention filters. All ingested spans are available for the last 15 minutes (rolling window), displayed without any sampling.

- [List view](#)
- [Timeseries View](#)

With the **List view**, you can:

- Monitor whether a new deployment went smoothly by filtering on `version_id` of all tags.
- View outage-related information in real time by searching 100% of ingested traces for a particular `org_id` or `customer_id` that is associated with a problematic child span.
- Check if a process has correctly started by typing `process_id` and autocompleting the new process ID as a tag on child spans.
- Monitor load test and performance impact on your endpoints by filtering on the duration of a child resource.
- Run one-click search queries on any span or tag directly from the trace panel view.
- Add, remove, and sort columns from span tags for a customized view.

The number of received spans per second is displayed at the top of the traces table. Since a stream of thousands of spans per second is not human readable, high throughput span streams show some spans for visual clarity. You can search for all available spans in the search query. Use the Live Search query bar filtering features to filter the spans stream and the **Pause/Play** button at the top right of the screen to pause or resume the stream.

[](https://datadog-docs.imgix.net/images/tracing/live_search/play-pause-button.d257328aba650995594f9132dff368ff.png?fit=max&auto=format)**Note**: Selecting any span pauses the stream and displays more details about the selected span in the trace side panel.

Visualize your spans as timeseries instead of a list using the **Timeseries view**. The Live Search Timeseries view is useful for graphing requests or errors that correspond to specified criteria, such as:

- Errors for the `ShoppingCart##checkout` service and endpoint, with a cart value of at least `$100`, with the ability to view traces matching these criteria individually.

- Monitor a canary deployment of a critical application update in real time.

- Compare latency across geographic regions scoped to the latest version of your iOS application.

In addition to showing timeseries for requests that match your queries, you can also visualize your spans as a top list of the most impacted customers, availability zones, or any other tag during an outage or investigation.

**Note:** Exporting to dashboards and monitors is only possible using retained spans.

### [Filtering](#filtering)

A valid query in the search bar displays traces that match your search criteria across **all spans**. The search syntax is the same in the Live Search views as in the other trace views, but here, your query is matched against all of the ingested traces across **any span** and **any tag**, and not just the indexed ones.

You can choose to query the [service entry spans](https://docs.datadoghq.com/glossary/#service-entry-span), the [root spans](https://docs.datadoghq.com/glossary/#trace-root-span), or all spans by changing the selection to the box above the trace table. Use this feature on high traffic applications to reduce the number of spans displayed and view only the entry point spans of the services or the entry point of the trace. Selecting this box only filters the spans shown in the list; the others are still shown in the flame graph when clicking on a span to view the trace details.

You can also filter on attributes that are not defined as facets. For example, to filter on the `cart.value` attribute, there are two options:

- Click on the `cart.value` attribute in the trace details panel and add it to the search query:

- Filter on all spans with a `cart.value` attribute by typing “cart.value” in the search query bar:

## [Indexed spans search with 15 day retention](#indexed-spans-search-with-15-day-retention)

[](https://datadog-docs.imgix.net/images/tracing/apm_lifecycle/trace_explorer_indexed_search.1927586fa426a486a071c3ae4f9cbe0d.png?fit=max&auto=format)You can search retained traces in the same way as you do a Live Search. To switch from searching live data to searching retained data, change the time selector to any period of time greater than 15 minutes. All spans that are indexed by retention filters are accessible from search. These spans are kept by Datadog for 15 days after being indexed by a retention filter.

- [List view](#)
- [Timeseries View](#)

All spans indexed by custom retention filters *and* the intelligent retention filter are available to be searched in the List view. However, if you filter by a tag that appears only on spans that are not indexed by any retention filter, your search does not return any results, unlike when using [Live Search](#live-search-for-15-minutes).

All spans indexed by custom retention filters or the intelligent retention filter are available to be searched when using trace analytics.

From the timeseries view, export your query to a [dashboard](https://docs.datadoghq.com/dashboards/widgets/timeseries/), [monitor](https://docs.datadoghq.com/monitors/types/apm/?tab=analytics), or [notebook](https://docs.datadoghq.com/notebooks) to investigate further or to alert automatically when an aggregate number of spans crosses a specific threshold.

**Note**: Spans indexed by the intelligent retention filter are excluded from APM trace analytics monitor evaluations. For more information, see [Trace Retention](https://docs.datadoghq.com/tracing/trace_pipeline/trace_retention/#trace-search-and-analytics-on-indexed-spans).

### [Retention configuration](#retention-configuration)

You can customize which spans are retained and at what retention rates. By default, [the Datadog intelligent retention filter](https://docs.datadoghq.com/tracing/trace_pipeline/trace_retention/#datadog-intelligent-retention-filter) is applied, which automatically retains traces with error and latency diversity as well as low-throughput resources. To learn more about the default intelligent retention filter and how to create your own additional filters, see the [retention filters documentation](https://docs.datadoghq.com/tracing/trace_pipeline/trace_retention/#retention-filters). Go to the [Retention Filters page](https://app.datadoghq.com/apm/traces/retention-filters) within the Datadog app to create or modify your own filters.

## [Further Reading](#further-reading)

Additional helpful documentation, links, and articles:

[Search SpansDOCUMENTATION

](https://docs.datadoghq.com/tracing/trace_explorer/search)