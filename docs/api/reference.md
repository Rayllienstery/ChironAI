# Chiron AI API Reference

> Generated from the live OpenAPI document. Do not edit by hand; run `python scripts/gen_api_docs.py`.

- OpenAPI: `3.1.0`
- Version: `0.8.56`
- Paths: `135`

Chiron AI STABLE OpenAPI description generated from Flask routes.

## Endpoints

### Chat

#### `POST /api/webui/chat`

**Summary:** Run WebUI chat request

Sends a CoreUI chat/test request through the configured provider and RAG proxy path.

- Operation ID: `webui_webui_chat_post`
- Flask endpoint: `webui.webui_chat`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Config

#### `GET /api/webui/config`

**Summary:** Get frontend runtime config

Returns lightweight configuration values needed by the CoreUI shell.

- Operation ID: `webui_get_config_get`
- Flask endpoint: `webui.get_config`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Crawler

#### `POST /api/webui/crawler/create-collection`

**Summary:** Create collection from crawl

Starts background indexing that builds a Qdrant collection from crawled content.

- Operation ID: `webui_create_collection_post`
- Flask endpoint: `webui.create_collection`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/crawler/create-collection-cancel/{job_id}`

**Summary:** Create crawler create collection cancel job id

Registered Flask endpoint `webui.cancel_create_collection` for `POST /api/webui/crawler/create-collection-cancel/{job_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_cancel_create_collection_post`
- Flask endpoint: `webui.cancel_create_collection`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/crawler/create-collection-status/{job_id}`

**Summary:** Get crawler create collection status job id

Registered Flask endpoint `webui.get_create_collection_status` for `GET /api/webui/crawler/create-collection-status/{job_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_create_collection_status_get`
- Flask endpoint: `webui.get_create_collection_status`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/crawler/indexer-tester/evaluate`

**Summary:** Create crawler indexer tester evaluate

Registered Flask endpoint `webui.indexer_tester_evaluate` for `POST /api/webui/crawler/indexer-tester/evaluate`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_indexer_tester_evaluate_post`
- Flask endpoint: `webui.indexer_tester_evaluate`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/crawler/indexer-tester/evaluate-batch`

**Summary:** Create crawler indexer tester evaluate batch

Registered Flask endpoint `webui.start_indexer_tester_evaluate_batch` for `POST /api/webui/crawler/indexer-tester/evaluate-batch`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_start_indexer_tester_evaluate_batch_post`
- Flask endpoint: `webui.start_indexer_tester_evaluate_batch`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/crawler/indexer-tester/evaluate-batch/detect-patterns`

**Summary:** Create crawler indexer tester evaluate batch detect patterns

Registered Flask endpoint `webui.detect_batch_eval_patterns` for `POST /api/webui/crawler/indexer-tester/evaluate-batch/detect-patterns`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_detect_batch_eval_patterns_post`
- Flask endpoint: `webui.detect_batch_eval_patterns`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/crawler/indexer-tester/evaluate-batch/status/{job_id}`

**Summary:** Get crawler indexer tester evaluate batch status job id

Registered Flask endpoint `webui.get_indexer_tester_evaluate_batch_status` for `GET /api/webui/crawler/indexer-tester/evaluate-batch/status/{job_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_indexer_tester_evaluate_batch_status_get`
- Flask endpoint: `webui.get_indexer_tester_evaluate_batch_status`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/crawler/indexer-tester/evaluate/`

**Summary:** Create crawler indexer tester evaluate

Registered Flask endpoint `webui.indexer_tester_evaluate` for `POST /api/webui/crawler/indexer-tester/evaluate/`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_indexer_tester_evaluate_post`
- Flask endpoint: `webui.indexer_tester_evaluate`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/crawler/indexer-tester/sources`

**Summary:** Get crawler indexer tester sources

Registered Flask endpoint `webui.get_indexer_tester_sources` for `GET /api/webui/crawler/indexer-tester/sources`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_indexer_tester_sources_get`
- Flask endpoint: `webui.get_indexer_tester_sources`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/crawler/indexer-tester/sources/{source_id}/files`

**Summary:** Get crawler indexer tester sources source id files

Registered Flask endpoint `webui.get_indexer_tester_files` for `GET /api/webui/crawler/indexer-tester/sources/{source_id}/files`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_indexer_tester_files_get`
- Flask endpoint: `webui.get_indexer_tester_files`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/crawler/indexer-tester/sources/{source_id}/files/{filename}`

**Summary:** Get crawler indexer tester sources source id files filename

Registered Flask endpoint `webui.get_indexer_tester_file_detail` for `GET /api/webui/crawler/indexer-tester/sources/{source_id}/files/{filename}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_indexer_tester_file_detail_get`
- Flask endpoint: `webui.get_indexer_tester_file_detail`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |
| filename | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/crawler/md-pipelines`

**Summary:** Get crawler md pipelines

Registered Flask endpoint `webui.get_md_pipelines_list` for `GET /api/webui/crawler/md-pipelines`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_md_pipelines_list_get`
- Flask endpoint: `webui.get_md_pipelines_list`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/crawler/md-pipelines/preview`

**Summary:** Create crawler md pipelines preview

Registered Flask endpoint `webui.preview_md_pipeline` for `POST /api/webui/crawler/md-pipelines/preview`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_preview_md_pipeline_post`
- Flask endpoint: `webui.preview_md_pipeline`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `DELETE /api/webui/crawler/md-pipelines/{name}`

**Summary:** Delete crawler md pipelines name

Registered Flask endpoint `webui.delete_md_pipeline` for `DELETE /api/webui/crawler/md-pipelines/{name}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_delete_md_pipeline_delete`
- Flask endpoint: `webui.delete_md_pipeline`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/crawler/md-pipelines/{name}`

**Summary:** Get crawler md pipelines name

Registered Flask endpoint `webui.get_md_pipeline` for `GET /api/webui/crawler/md-pipelines/{name}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_md_pipeline_get`
- Flask endpoint: `webui.get_md_pipeline`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/crawler/md-pipelines/{name}`

**Summary:** Create crawler md pipelines name

Registered Flask endpoint `webui.save_md_pipeline` for `POST /api/webui/crawler/md-pipelines/{name}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_save_md_pipeline_post`
- Flask endpoint: `webui.save_md_pipeline`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `PUT /api/webui/crawler/md-pipelines/{name}`

**Summary:** Update crawler md pipelines name

Registered Flask endpoint `webui.save_md_pipeline` for `PUT /api/webui/crawler/md-pipelines/{name}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_save_md_pipeline_put`
- Flask endpoint: `webui.save_md_pipeline`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/crawler/sources`

**Summary:** List crawler sources

Returns configured crawl sources with status metadata for CoreUI.

- Operation ID: `webui_get_crawler_sources_get`
- Flask endpoint: `webui.get_crawler_sources`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/crawler/sources`

**Summary:** Create crawler source

Registers a new crawl source from submitted configuration.

- Operation ID: `webui_add_crawler_source_post`
- Flask endpoint: `webui.add_crawler_source`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/crawler/sources/{source_id}`

**Summary:** Get crawler source

Returns one crawl source definition and runtime status.

- Operation ID: `webui_get_crawler_source_get`
- Flask endpoint: `webui.get_crawler_source`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `PUT /api/webui/crawler/sources/{source_id}`

**Summary:** Update crawler sources source id

Registered Flask endpoint `webui.update_crawler_source` for `PUT /api/webui/crawler/sources/{source_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_crawler_source_put`
- Flask endpoint: `webui.update_crawler_source`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/crawler/sources/{source_id}/crawl`

**Summary:** Start source crawl job

Starts or resumes crawling for the given source id.

- Operation ID: `webui_crawl_source_endpoint_post`
- Flask endpoint: `webui.crawl_source_endpoint`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/crawler/sources/{source_id}/crawl/status`

**Summary:** Get crawl job status

Returns progress and last error for an active or recent crawl job.

- Operation ID: `webui_get_crawl_status_get`
- Flask endpoint: `webui.get_crawl_status`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/crawler/sources/{source_id}/pages`

**Summary:** Get crawler sources source id pages

Registered Flask endpoint `webui.get_crawler_source_pages` for `GET /api/webui/crawler/sources/{source_id}/pages`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_crawler_source_pages_get`
- Flask endpoint: `webui.get_crawler_source_pages`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/crawler/sources/{source_id}/stats`

**Summary:** Get crawler sources source id stats

Registered Flask endpoint `webui.get_crawler_source_stats` for `GET /api/webui/crawler/sources/{source_id}/stats`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_crawler_source_stats_get`
- Flask endpoint: `webui.get_crawler_source_stats`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| source_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Dashboard Metrics

#### `GET /api/webui/dashboard-metrics`

**Summary:** Get dashboard metrics

Registered Flask endpoint `webui.dashboard_metrics` for `GET /api/webui/dashboard-metrics`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_dashboard_metrics_get`
- Flask endpoint: `webui.dashboard_metrics`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Dependencies

#### `GET /api/webui/dependencies`

**Summary:** List project dependencies

Returns Python, npm, and Docker dependency inventory plus update capabilities.

- Operation ID: `webui_get_dependencies_get`
- Flask endpoint: `webui.get_dependencies`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Dependency inventory. | application/json: DependenciesResponse |

#### `POST /api/webui/dependencies/check-updates`

**Summary:** Check dependency updates

Starts a dependency job that checks available package updates.

- Operation ID: `webui_check_dependency_updates_post`
- Flask endpoint: `webui.check_dependency_updates`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/dependencies/jobs/{job_id}`

**Summary:** Get dependency job

Returns live status, output, and result metadata for a dependency job.

- Operation ID: `webui_get_dependency_job_get`
- Flask endpoint: `webui.get_dependency_job`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Dependency job status. | application/json: DependencyJobResponse |

#### `POST /api/webui/dependencies/update`

**Summary:** Update dependencies

Starts a dependency job that applies supported dependency updates.

- Operation ID: `webui_update_dependencies_post`
- Flask endpoint: `webui.update_dependencies`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Dev Console

#### `GET /api/webui/dev-console`

**Summary:** Get dev console

Registered Flask endpoint `webui.get_dev_console` for `GET /api/webui/dev-console`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_dev_console_get`
- Flask endpoint: `webui.get_dev_console`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Docker

#### `DELETE /api/webui/docker/containers`

**Summary:** Delete docker containers

Registered Flask endpoint `webui.docker_remove_container` for `DELETE /api/webui/docker/containers`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_docker_remove_container_delete`
- Flask endpoint: `webui.docker_remove_container`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/docker/containers`

**Summary:** List Docker containers

Returns containers visible to the DockerManager host capability.

- Operation ID: `webui_docker_containers_get`
- Flask endpoint: `webui.docker_containers`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Docker containers. | application/json: DockerListResponse |

#### `POST /api/webui/docker/containers/start`

**Summary:** Create docker containers start

Registered Flask endpoint `webui.docker_start_container` for `POST /api/webui/docker/containers/start`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_docker_start_container_post`
- Flask endpoint: `webui.docker_start_container`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/docker/containers/stop`

**Summary:** Create docker containers stop

Registered Flask endpoint `webui.docker_stop_container` for `POST /api/webui/docker/containers/stop`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_docker_stop_container_post`
- Flask endpoint: `webui.docker_stop_container`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/docker/events`

**Summary:** Stream Docker events

Server-sent event stream for Docker container and image changes.

- Operation ID: `webui_docker_events_get`
- Flask endpoint: `webui.docker_events`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `DELETE /api/webui/docker/images`

**Summary:** Delete docker images

Registered Flask endpoint `webui.docker_remove_image` for `DELETE /api/webui/docker/images`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_docker_remove_image_delete`
- Flask endpoint: `webui.docker_remove_image`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/docker/images`

**Summary:** List Docker images

Returns local Docker images visible to the DockerManager host capability.

- Operation ID: `webui_docker_images_get`
- Flask endpoint: `webui.docker_images`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Docker images. | application/json: DockerListResponse |

#### `POST /api/webui/docker/images/check-update`

**Summary:** Create docker images check update

Registered Flask endpoint `webui.docker_check_image_update` for `POST /api/webui/docker/images/check-update`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_docker_check_image_update_post`
- Flask endpoint: `webui.docker_check_image_update`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/docker/images/pull`

**Summary:** Create docker images pull

Registered Flask endpoint `webui.docker_pull_image` for `POST /api/webui/docker/images/pull`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_docker_pull_image_post`
- Flask endpoint: `webui.docker_pull_image`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/docker/images/update`

**Summary:** Create docker images update

Registered Flask endpoint `webui.docker_update_image` for `POST /api/webui/docker/images/update`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_docker_update_image_post`
- Flask endpoint: `webui.docker_update_image`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/docker/status`

**Summary:** Get Docker status

Returns Docker availability and host diagnostics used by the Docker tab.

- Operation ID: `webui_docker_status_get`
- Flask endpoint: `webui.docker_status`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Docker runtime status. | application/json: DockerStatusResponse |

### Extensions

#### `POST /api/webui/extensions/disable`

**Summary:** Disable extension

Disables an installed extension and refreshes extension runtime state.

- Operation ID: `webui_disable_extension_post`
- Flask endpoint: `webui.disable_extension`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/extensions/docker/update`

**Summary:** Create extensions docker update

Registered Flask endpoint `webui.update_extension_docker` for `POST /api/webui/extensions/docker/update`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_extension_docker_post`
- Flask endpoint: `webui.update_extension_docker`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/extensions/enable`

**Summary:** Enable extension

Enables an installed extension and refreshes extension runtime state.

- Operation ID: `webui_enable_extension_post`
- Flask endpoint: `webui.enable_extension`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/extensions/install`

**Summary:** Install extension

Installs an extension from the trusted registry metadata and returns lifecycle status.

- Operation ID: `webui_install_extension_post`
- Flask endpoint: `webui.install_extension`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/extensions/installed`

**Summary:** List installed extensions

Returns locally installed extensions, runtime status, security status, and optional Docker update metadata.

- Operation ID: `webui_get_installed_extensions_get`
- Flask endpoint: `webui.get_installed_extensions`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Installed extensions. | application/json: InstalledExtensionsResponse |

#### `GET /api/webui/extensions/providers`

**Summary:** List extension providers

Returns provider descriptors contributed by installed extensions.

- Operation ID: `webui_get_extension_providers_get`
- Flask endpoint: `webui.get_extension_providers`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/extensions/registry`

**Summary:** List registry extensions

Returns installable extension cards from the configured registry, including publisher and capability metadata.

- Operation ID: `webui_get_extensions_registry_get`
- Flask endpoint: `webui.get_extensions_registry`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Extension registry cards. | application/json: ExtensionRegistryResponse |

#### `POST /api/webui/extensions/remove`

**Summary:** Remove extension

Removes an installed extension and reports whether backend restart is required.

- Operation ID: `webui_remove_extension_post`
- Flask endpoint: `webui.remove_extension`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/extensions/tabs`

**Summary:** List extension tabs

Returns extension-owned CoreUI tab descriptors, including iframe/declarative UI metadata and cached load state.

- Operation ID: `webui_get_extension_tabs_get`
- Flask endpoint: `webui.get_extension_tabs`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Available extension tabs. | application/json: ExtensionTabsResponse |

#### `GET /api/webui/extensions/ui`

**Summary:** Get extension UI schemas

Returns declarative settings/status UI schemas contributed by installed extensions.

- Operation ID: `webui_get_extension_ui_payload_get`
- Flask endpoint: `webui.get_extension_ui_payload`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Extension UI schema payload. | application/json: GenericObject |

#### `POST /api/webui/extensions/{extension_id}/actions/{action_id}`

**Summary:** Run extension action

Invokes an extension-owned action through the supported host runtime boundary.

- Operation ID: `webui_run_extension_action_post`
- Flask endpoint: `webui.run_extension_action`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| extension_id | path | True | string |
| action_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/extensions/{extension_id}/assets/{asset_path}`

**Summary:** Get extensions extension id assets asset path

Registered Flask endpoint `webui.get_extension_asset` for `GET /api/webui/extensions/{extension_id}/assets/{asset_path}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_extension_asset_get`
- Flask endpoint: `webui.get_extension_asset`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| extension_id | path | True | string |
| asset_path | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/extensions/{extension_id}/details`

**Summary:** Get extension details

Returns registry details, versions, README metadata, publisher metadata, and warnings for an extension.

- Operation ID: `webui_get_extension_details_get`
- Flask endpoint: `webui.get_extension_details`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| extension_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/extensions/{extension_id}/sandbox/kill`

**Summary:** Create extensions extension id sandbox kill

Registered Flask endpoint `webui.kill_extension_sandbox` for `POST /api/webui/extensions/{extension_id}/sandbox/kill`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_kill_extension_sandbox_post`
- Flask endpoint: `webui.kill_extension_sandbox`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| extension_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/extensions/{extension_id}/sandbox/restart`

**Summary:** Create extensions extension id sandbox restart

Registered Flask endpoint `webui.restart_extension_sandbox` for `POST /api/webui/extensions/{extension_id}/sandbox/restart`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_restart_extension_sandbox_post`
- Flask endpoint: `webui.restart_extension_sandbox`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| extension_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/extensions/{extension_id}/tab`

**Summary:** Get extension tab payload

Returns the render payload for one extension-owned tab.

- Operation ID: `webui_get_extension_tab_get`
- Flask endpoint: `webui.get_extension_tab`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| extension_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/extensions/{extension_id}/tab/refresh`

**Summary:** Refresh extension tab payload

Starts or reuses a background refresh job for one extension tab payload.

- Operation ID: `webui_refresh_extension_tab_post`
- Flask endpoint: `webui.refresh_extension_tab`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| extension_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Health

#### `GET /api/webui/health`

**Summary:** Get health

Registered Flask endpoint `webui.webui_health` for `GET /api/webui/health`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_webui_health_get`
- Flask endpoint: `webui.webui_health`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /health`

**Summary:** Check ChironAI stack health

Returns aggregate health for the local proxy host and required runtime services.

- Operation ID: `health_get`
- Flask endpoint: `health`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Help

#### `GET /api/webui/help`

**Summary:** List help articles

Returns the in-app help knowledge base index (slug, title, tags) for CoreUI Help.

- Operation ID: `webui_list_help_articles_get`
- Flask endpoint: `webui.list_help_articles`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/help/search`

**Summary:** Search help articles

Searches help titles, tags, and bodies. Query parameter ``q`` is required.

- Operation ID: `webui_search_help_articles_get`
- Flask endpoint: `webui.search_help_articles`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/help/{slug}`

**Summary:** Get help article

Returns one bundled markdown help article by slug.

- Operation ID: `webui_get_help_article_get`
- Flask endpoint: `webui.get_help_article`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| slug | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Live

#### `GET /live`

**Summary:** Get live

Registered Flask endpoint `live` for `GET /live`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `live_get`
- Flask endpoint: `live`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Llm Proxy

#### `DELETE /api/webui/llm-proxy/api-key`

**Summary:** Delete llm proxy api key

Registered Flask endpoint `webui.llm_proxy_delete_api_key` for `DELETE /api/webui/llm-proxy/api-key`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_llm_proxy_delete_api_key_delete`
- Flask endpoint: `webui.llm_proxy_delete_api_key`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/llm-proxy/api-key`

**Summary:** Get llm proxy api key

Registered Flask endpoint `webui.llm_proxy_api_key_status` for `GET /api/webui/llm-proxy/api-key`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_llm_proxy_api_key_status_get`
- Flask endpoint: `webui.llm_proxy_api_key_status`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/llm-proxy/api-key/generate`

**Summary:** Create llm proxy api key generate

Registered Flask endpoint `webui.llm_proxy_generate_api_key` for `POST /api/webui/llm-proxy/api-key/generate`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_llm_proxy_generate_api_key_post`
- Flask endpoint: `webui.llm_proxy_generate_api_key`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/llm-proxy/api-key/reveal`

**Summary:** Create llm proxy api key reveal

Registered Flask endpoint `webui.llm_proxy_reveal_api_key` for `POST /api/webui/llm-proxy/api-key/reveal`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_llm_proxy_reveal_api_key_post`
- Flask endpoint: `webui.llm_proxy_reveal_api_key`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/llm-proxy/builds`

**Summary:** List LLM proxy builds

Returns configured OpenAI-compatible model builds and diagnostic metadata for CoreUI.

- Operation ID: `webui_get_llm_proxy_builds_get`
- Flask endpoint: `webui.get_llm_proxy_builds`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Configured proxy builds. | application/json: LlmProxyBuildsGetResponse |

#### `PUT /api/webui/llm-proxy/builds`

**Summary:** Replace LLM proxy builds

Validates and persists the submitted build list used by /v1 model routing.

- Operation ID: `webui_put_llm_proxy_builds_put`
- Flask endpoint: `webui.put_llm_proxy_builds`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Updated proxy builds. | application/json: LlmProxyBuildsPutOkResponse |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/llm-proxy/builds/preview-model`

**Summary:** Preview upstream model

Returns provider metadata for a model before saving it into an LLM proxy build.

- Operation ID: `webui_llm_proxy_build_preview_model_post`
- Flask endpoint: `webui.llm_proxy_build_preview_model`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/llm-proxy/builds/{build_id}`

**Summary:** Get LLM proxy build

Returns one configured proxy build by id, including diagnostics when available.

- Operation ID: `webui_get_llm_proxy_build_one_get`
- Flask endpoint: `webui.get_llm_proxy_build_one`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| build_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/llm-proxy/status`

**Summary:** Get LLM proxy status

Returns the CoreUI status card payload for the local OpenAI-compatible LLM proxy.

- Operation ID: `webui_llm_proxy_status_get`
- Flask endpoint: `webui.llm_proxy_status`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | LLM proxy status. | application/json: LlmProxyStatusResponse |

#### `GET /v1`

**Summary:** Get OpenAI-compatible API root

Returns a lightweight marker for clients configured with the /v1 base URL.

- Operation ID: `llm_proxy_v1_v1_root_get`
- Flask endpoint: `llm_proxy_v1.v1_root`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OpenAI-compatible API root. | application/json: GenericObject |

#### `POST /v1`

**Summary:** Run chat completion from /v1 root

Compatibility endpoint for clients that POST chat-shaped payloads to the /v1 base URL.

- Operation ID: `llm_proxy_v1_v1_root_post`
- Flask endpoint: `llm_proxy_v1.v1_root`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /v1/chat/completions`

**Summary:** Create chat completion

OpenAI-compatible chat completions endpoint with ChironAI RAG/proxy extensions.

- Operation ID: `llm_proxy_v1_chat_completions_post`
- Flask endpoint: `llm_proxy_v1.chat_completions`
- Request body: `application/json: OpenAiChatCompletionRequest`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OpenAI-compatible chat completion. | application/json: OpenAiChatCompletionResponse |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /v1/external-docs/ingest`

**Summary:** Create v1 external docs ingest

Registered Flask endpoint `llm_proxy_v1.external_docs_ingest` for `POST /v1/external-docs/ingest`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `llm_proxy_v1_external_docs_ingest_post`
- Flask endpoint: `llm_proxy_v1.external_docs_ingest`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | External documentation ingestion. | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /v1/files/apply-edit`

**Summary:** Create v1 files apply edit

Registered Flask endpoint `llm_proxy_v1.apply_file_edit` for `POST /v1/files/apply-edit`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `llm_proxy_v1_apply_file_edit_post`
- Flask endpoint: `llm_proxy_v1.apply_file_edit`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Apply file edit request. | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /v1/messages`

**Summary:** Create Anthropic-compatible message

Anthropic Messages compatibility endpoint translated into the ChironAI chat pipeline.

- Operation ID: `llm_proxy_v1_anthropic_messages_post`
- Flask endpoint: `llm_proxy_v1.anthropic_messages`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Anthropic-compatible messages endpoint. | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /v1/models`

**Summary:** List OpenAI-compatible models

Returns model objects exposed by configured LLM proxy builds.

- Operation ID: `llm_proxy_v1_list_models_get`
- Flask endpoint: `llm_proxy_v1.list_models`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OpenAI-compatible model list. | application/json: OpenAiModelListResponse |

#### `GET /v1/models/{model_id}`

**Summary:** Retrieve OpenAI-compatible model

Returns one model object, including compatibility capability aliases for IDE clients.

- Operation ID: `llm_proxy_v1_retrieve_model_get`
- Flask endpoint: `llm_proxy_v1.retrieve_model`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| model_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OpenAI-compatible model metadata. | application/json: OpenAiModelResponse |

#### `POST /v1/responses`

**Summary:** Create response

OpenAI Responses compatibility endpoint mapped onto the ChironAI chat pipeline.

- Operation ID: `llm_proxy_v1_responses_post`
- Flask endpoint: `llm_proxy_v1.responses`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OpenAI-compatible responses endpoint. | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Logs

#### `DELETE /api/webui/logs`

**Summary:** Delete logs

Registered Flask endpoint `webui.delete_logs` for `DELETE /api/webui/logs`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_delete_logs_delete`
- Flask endpoint: `webui.delete_logs`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/logs`

**Summary:** Get logs

Registered Flask endpoint `webui.get_logs` for `GET /api/webui/logs`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_logs_get`
- Flask endpoint: `webui.get_logs`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/logs`

**Summary:** Create logs

Registered Flask endpoint `webui.create_log` for `POST /api/webui/logs`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_create_log_post`
- Flask endpoint: `webui.create_log`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Metrics

#### `GET /metrics`

**Summary:** Export Prometheus metrics

Returns Prometheus text exposition for HTTP request counts, latency, and observability gauges.

- Operation ID: `metrics_get`
- Flask endpoint: `metrics`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Model Settings

#### `GET /api/webui/model-settings`

**Summary:** Get proxy model settings

Returns the persisted RAG/proxy settings used by the model tester and chat surfaces.

- Operation ID: `webui_get_model_settings_get`
- Flask endpoint: `webui.get_model_settings`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Current proxy model settings. | application/json: ModelSettingsGetResponse |

#### `POST /api/webui/model-settings`

**Summary:** Update proxy model settings

Merges submitted fields into the stored proxy settings blob and returns the effective settings.

- Operation ID: `webui_update_model_settings_post`
- Flask endpoint: `webui.update_model_settings`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Updated proxy model settings. | application/json: ModelSettingsPostResponse |
| 400 | Bad request | application/json: ErrorResponse |

### Models

#### `GET /api/webui/models`

**Summary:** List chat models

Returns provider-backed model rows available to CoreUI model pickers.

- Operation ID: `webui_get_models_get`
- Flask endpoint: `webui.get_models`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Available provider models. | application/json: ModelsListResponse |

### Notifications

#### `GET /api/webui/notifications`

**Summary:** List CoreUI notifications

Returns persisted notification center entries for a browser session. Query parameter ``session_id`` is required.

- Operation ID: `webui_get_coreui_notifications_get`
- Flask endpoint: `webui.get_coreui_notifications`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | CoreUI notification list. | application/json: NotificationsListResponse |

#### `POST /api/webui/notifications`

**Summary:** Create CoreUI notification

Persists an error, event, or info notification for the CoreUI notification center.

- Operation ID: `webui_create_coreui_notification_post`
- Flask endpoint: `webui.create_coreui_notification`
- Request body: `application/json: NotificationCreateRequest`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Created notification id. | application/json: NotificationCreateResponse |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/notifications/clear`

**Summary:** Clear CoreUI notifications

Deletes all persisted notifications for a session. Live activity cards are unaffected.

- Operation ID: `webui_clear_coreui_notifications_post`
- Flask endpoint: `webui.clear_coreui_notifications`
- Request body: `application/json: NotificationsClearRequest`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Clear result. | application/json: NotificationsClearResponse |
| 400 | Bad request | application/json: ErrorResponse |

#### `PATCH /api/webui/notifications/{nid}/dismiss`

**Summary:** Dismiss CoreUI notification

Marks a persisted notification as dismissed for the requesting session.

- Operation ID: `webui_dismiss_coreui_notification_patch`
- Flask endpoint: `webui.dismiss_coreui_notification`
- Request body: `application/json: NotificationDismissRequest`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| nid | path | True | integer |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Dismiss acknowledgement. | application/json: NotificationDismissResponse |
| 400 | Bad request | application/json: ErrorResponse |

### Performance

#### `POST /api/webui/performance/browser-timing`

**Summary:** Submit browser timing

Stores browser Navigation Timing and CoreUI lifecycle measurements for the performance tab.

- Operation ID: `webui_post_browser_timing_post`
- Flask endpoint: `webui.post_browser_timing`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/performance/startup`

**Summary:** Get startup performance

Returns backend startup phases and browser timing submitted by CoreUI.

- Operation ID: `webui_get_startup_performance_get`
- Flask endpoint: `webui.get_startup_performance`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Startup timing report. | application/json: StartupPerformanceResponse |

### Pipeline Definition

#### `GET /api/webui/pipeline-definition`

**Summary:** Get pipeline definition

Registered Flask endpoint `webui.get_pipeline_definition` for `GET /api/webui/pipeline-definition`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_pipeline_definition_get`
- Flask endpoint: `webui.get_pipeline_definition`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Pipeline Preview

#### `GET /api/webui/pipeline-preview`

**Summary:** Get pipeline preview

Registered Flask endpoint `webui.get_pipeline_preview` for `GET /api/webui/pipeline-preview`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_pipeline_preview_get`
- Flask endpoint: `webui.get_pipeline_preview`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Prompts

#### `GET /api/webui/prompts`

**Summary:** List prompt templates

Returns saved prompt template names and ids for CoreUI prompt selectors.

- Operation ID: `webui_get_prompts_get`
- Flask endpoint: `webui.get_prompts`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/prompts`

**Summary:** Create prompt template

Creates a new prompt template from submitted name/content fields.

- Operation ID: `webui_create_prompt_post`
- Flask endpoint: `webui.create_prompt`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `DELETE /api/webui/prompts/trash`

**Summary:** Delete prompts trash

Registered Flask endpoint `webui.clear_trash` for `DELETE /api/webui/prompts/trash`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_clear_trash_delete`
- Flask endpoint: `webui.clear_trash`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/prompts/trash`

**Summary:** Get prompts trash

Registered Flask endpoint `webui.get_trash_prompts` for `GET /api/webui/prompts/trash`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_trash_prompts_get`
- Flask endpoint: `webui.get_trash_prompts`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/prompts/trash/{trash_name}`

**Summary:** Get prompts trash trash name

Registered Flask endpoint `webui.get_trash_prompt_content` for `GET /api/webui/prompts/trash/{trash_name}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_trash_prompt_content_get`
- Flask endpoint: `webui.get_trash_prompt_content`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| trash_name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `PUT /api/webui/prompts/trash/{trash_name}`

**Summary:** Update prompts trash trash name

Registered Flask endpoint `webui.update_trash_prompt` for `PUT /api/webui/prompts/trash/{trash_name}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_trash_prompt_put`
- Flask endpoint: `webui.update_trash_prompt`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| trash_name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/prompts/trash/{trash_name}/restore`

**Summary:** Create prompts trash trash name restore

Registered Flask endpoint `webui.restore_prompt` for `POST /api/webui/prompts/trash/{trash_name}/restore`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_restore_prompt_post`
- Flask endpoint: `webui.restore_prompt`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| trash_name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `DELETE /api/webui/prompts/{name}`

**Summary:** Delete prompt template

Moves a named prompt template to prompt trash.

- Operation ID: `webui_delete_prompt_delete`
- Flask endpoint: `webui.delete_prompt`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/prompts/{name}`

**Summary:** Get prompt template

Returns the full content for a named prompt template.

- Operation ID: `webui_get_prompt_content_get`
- Flask endpoint: `webui.get_prompt_content`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `PUT /api/webui/prompts/{name}`

**Summary:** Update prompt template

Renames and/or updates the content for a named prompt template.

- Operation ID: `webui_update_prompt_put`
- Flask endpoint: `webui.update_prompt`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Providers

#### `GET /api/webui/providers/catalog`

**Summary:** Get provider catalog

Returns all available LLM providers and model descriptors for CoreUI pickers.

- Operation ID: `webui_get_provider_catalog_get`
- Flask endpoint: `webui.get_provider_catalog`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Provider catalog. | application/json: GenericObject |

#### `GET /api/webui/providers/custom`

**Summary:** Get providers custom

Registered Flask endpoint `webui.list_custom_providers` for `GET /api/webui/providers/custom`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_list_custom_providers_get`
- Flask endpoint: `webui.list_custom_providers`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/providers/custom`

**Summary:** Create providers custom

Registered Flask endpoint `webui.create_custom_provider` for `POST /api/webui/providers/custom`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_create_custom_provider_post`
- Flask endpoint: `webui.create_custom_provider`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `DELETE /api/webui/providers/custom/{provider_id}`

**Summary:** Delete providers custom provider id

Registered Flask endpoint `webui.delete_custom_provider_route` for `DELETE /api/webui/providers/custom/{provider_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_delete_custom_provider_route_delete`
- Flask endpoint: `webui.delete_custom_provider_route`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| provider_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `PUT /api/webui/providers/custom/{provider_id}`

**Summary:** Update providers custom provider id

Registered Flask endpoint `webui.update_custom_provider` for `PUT /api/webui/providers/custom/{provider_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_custom_provider_put`
- Flask endpoint: `webui.update_custom_provider`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| provider_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/providers/custom/{provider_id}/test`

**Summary:** Create providers custom provider id test

Registered Flask endpoint `webui.test_custom_provider` for `POST /api/webui/providers/custom/{provider_id}/test`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_test_custom_provider_post`
- Flask endpoint: `webui.test_custom_provider`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| provider_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Proxy Journal

#### `DELETE /api/webui/proxy-journal`

**Summary:** Delete proxy journal

Registered Flask endpoint `webui.delete_proxy_journal` for `DELETE /api/webui/proxy-journal`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_delete_proxy_journal_delete`
- Flask endpoint: `webui.delete_proxy_journal`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/proxy-journal`

**Summary:** Get proxy journal

Registered Flask endpoint `webui.get_proxy_journal` for `GET /api/webui/proxy-journal`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_proxy_journal_get`
- Flask endpoint: `webui.get_proxy_journal`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Proxy Logs

#### `DELETE /api/webui/proxy-logs`

**Summary:** Delete proxy logs

Registered Flask endpoint `webui.delete_proxy_logs` for `DELETE /api/webui/proxy-logs`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_delete_proxy_logs_delete`
- Flask endpoint: `webui.delete_proxy_logs`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/proxy-logs`

**Summary:** Get proxy logs

Registered Flask endpoint `webui.get_proxy_logs` for `GET /api/webui/proxy-logs`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_proxy_logs_get`
- Flask endpoint: `webui.get_proxy_logs`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Proxy Trace

#### `GET /api/webui/proxy-trace/current`

**Summary:** Get proxy trace current

Registered Flask endpoint `webui.get_proxy_trace_current` for `GET /api/webui/proxy-trace/current`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_proxy_trace_current_get`
- Flask endpoint: `webui.get_proxy_trace_current`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Proxy Traces

#### `GET /api/webui/proxy-traces`

**Summary:** Get proxy traces

Registered Flask endpoint `webui.get_proxy_traces` for `GET /api/webui/proxy-traces`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_proxy_traces_get`
- Flask endpoint: `webui.get_proxy_traces`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/proxy-traces/clear`

**Summary:** Create proxy traces clear

Registered Flask endpoint `webui.post_proxy_traces_clear` for `POST /api/webui/proxy-traces/clear`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_post_proxy_traces_clear_post`
- Flask endpoint: `webui.post_proxy_traces_clear`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Rag

#### `POST /api/webui/rag/collection-settings`

**Summary:** Create rag collection settings

Registered Flask endpoint `webui.save_rag_collection_settings` for `POST /api/webui/rag/collection-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_save_rag_collection_settings_post`
- Flask endpoint: `webui.save_rag_collection_settings`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/rag/collections`

**Summary:** List RAG collections

Returns Qdrant collections and metadata for CoreUI collection selectors.

- Operation ID: `webui_rag_collections_get`
- Flask endpoint: `webui.rag_collections`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | RAG collections. | application/json: RagCollectionsResponse |

#### `DELETE /api/webui/rag/collections/{collection_name}`

**Summary:** Delete RAG collection

Deletes a named Qdrant collection after frontend confirmation.

- Operation ID: `webui_delete_rag_collection_delete`
- Flask endpoint: `webui.delete_rag_collection`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| collection_name | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/rag/start`

**Summary:** Start RAG service

Starts the local RAG/Qdrant service through the configured runtime boundary.

- Operation ID: `webui_rag_start_post`
- Flask endpoint: `webui.rag_start`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/rag/status`

**Summary:** Get RAG status

Returns Qdrant/RAG availability and collection status used by dashboard cards.

- Operation ID: `webui_rag_status_get`
- Flask endpoint: `webui.rag_status`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | RAG service status. | application/json: RagStatusResponse |

#### `POST /api/webui/rag/stop`

**Summary:** Stop RAG service

Stops the local RAG/Qdrant service through the configured runtime boundary.

- Operation ID: `webui_rag_stop_post`
- Flask endpoint: `webui.rag_stop`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Rag Framework Settings

#### `GET /api/webui/rag-framework-settings`

**Summary:** Get rag framework settings

Registered Flask endpoint `webui.get_rag_framework_settings` for `GET /api/webui/rag-framework-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_rag_framework_settings_get`
- Flask endpoint: `webui.get_rag_framework_settings`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/rag-framework-settings`

**Summary:** Create rag framework settings

Registered Flask endpoint `webui.update_rag_framework_settings` for `POST /api/webui/rag-framework-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_rag_framework_settings_post`
- Flask endpoint: `webui.update_rag_framework_settings`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Rag Keyword Collections

#### `GET /api/webui/rag-keyword-collections`

**Summary:** Get rag keyword collections

Registered Flask endpoint `webui.get_rag_keyword_collections` for `GET /api/webui/rag-keyword-collections`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_rag_keyword_collections_get`
- Flask endpoint: `webui.get_rag_keyword_collections`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/rag-keyword-collections`

**Summary:** Create rag keyword collections

Registered Flask endpoint `webui.update_rag_keyword_collections` for `POST /api/webui/rag-keyword-collections`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_rag_keyword_collections_post`
- Flask endpoint: `webui.update_rag_keyword_collections`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `DELETE /api/webui/rag-keyword-collections/{collection_id}`

**Summary:** Delete rag keyword collections collection id

Registered Flask endpoint `webui.delete_rag_keyword_collection` for `DELETE /api/webui/rag-keyword-collections/{collection_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_delete_rag_keyword_collection_delete`
- Flask endpoint: `webui.delete_rag_keyword_collection`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| collection_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Rag Model Settings

#### `GET /api/webui/rag-model-settings`

**Summary:** Get rag model settings

Registered Flask endpoint `webui.get_rag_model_settings` for `GET /api/webui/rag-model-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_rag_model_settings_get`
- Flask endpoint: `webui.get_rag_model_settings`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/rag-model-settings`

**Summary:** Create rag model settings

Registered Flask endpoint `webui.update_rag_model_settings` for `POST /api/webui/rag-model-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_rag_model_settings_post`
- Flask endpoint: `webui.update_rag_model_settings`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Rag Tests

#### `GET /api/webui/rag-tests`

**Summary:** Get rag tests

Registered Flask endpoint `rag_tests.rag_tests_list` for `GET /api/webui/rag-tests`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_list_get`
- Flask endpoint: `rag_tests.rag_tests_list`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/rag-tests`

**Summary:** Create rag tests

Registered Flask endpoint `rag_tests.rag_tests_create` for `POST /api/webui/rag-tests`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_create_post`
- Flask endpoint: `rag_tests.rag_tests_create`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/rag-tests/filters`

**Summary:** Get rag tests filters

Registered Flask endpoint `rag_tests.rag_tests_filters` for `GET /api/webui/rag-tests/filters`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_filters_get`
- Flask endpoint: `rag_tests.rag_tests_filters`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/rag-tests/run`

**Summary:** Create rag tests run

Registered Flask endpoint `rag_tests.rag_tests_run` for `POST /api/webui/rag-tests/run`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_run_post`
- Flask endpoint: `rag_tests.rag_tests_run`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/rag-tests/run/cancel/{job_id}`

**Summary:** Create rag tests run cancel job id

Registered Flask endpoint `rag_tests.rag_tests_run_cancel` for `POST /api/webui/rag-tests/run/cancel/{job_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_run_cancel_post`
- Flask endpoint: `rag_tests.rag_tests_run_cancel`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/rag-tests/run/status/{job_id}`

**Summary:** Get rag tests run status job id

Registered Flask endpoint `rag_tests.rag_tests_run_status` for `GET /api/webui/rag-tests/run/status/{job_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_run_status_get`
- Flask endpoint: `rag_tests.rag_tests_run_status`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `DELETE /api/webui/rag-tests/runs`

**Summary:** Delete rag tests runs

Registered Flask endpoint `rag_tests.rag_tests_runs_delete` for `DELETE /api/webui/rag-tests/runs`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_runs_delete_delete`
- Flask endpoint: `rag_tests.rag_tests_runs_delete`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/rag-tests/runs`

**Summary:** Get rag tests runs

Registered Flask endpoint `rag_tests.rag_tests_runs_list` for `GET /api/webui/rag-tests/runs`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_runs_list_get`
- Flask endpoint: `rag_tests.rag_tests_runs_list`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/rag-tests/runs/summary`

**Summary:** Get rag tests runs summary

Registered Flask endpoint `rag_tests.rag_tests_runs_summary` for `GET /api/webui/rag-tests/runs/summary`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_runs_summary_get`
- Flask endpoint: `rag_tests.rag_tests_runs_summary`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/rag-tests/runs/{run_id}`

**Summary:** Get rag tests runs run id

Registered Flask endpoint `rag_tests.rag_tests_run_detail` for `GET /api/webui/rag-tests/runs/{run_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_run_detail_get`
- Flask endpoint: `rag_tests.rag_tests_run_detail`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| run_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `GET /api/webui/rag-tests/runs/{run_id}/export`

**Summary:** Get rag tests runs run id export

Registered Flask endpoint `rag_tests.rag_tests_run_export` for `GET /api/webui/rag-tests/runs/{run_id}/export`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_run_export_get`
- Flask endpoint: `rag_tests.rag_tests_run_export`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| run_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `DELETE /api/webui/rag-tests/{test_id}`

**Summary:** Delete rag tests test id

Registered Flask endpoint `rag_tests.rag_tests_delete` for `DELETE /api/webui/rag-tests/{test_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_delete_delete`
- Flask endpoint: `rag_tests.rag_tests_delete`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| test_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/rag-tests/{test_id}`

**Summary:** Get rag tests test id

Registered Flask endpoint `rag_tests.rag_tests_get_one` for `GET /api/webui/rag-tests/{test_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_get_one_get`
- Flask endpoint: `rag_tests.rag_tests_get_one`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| test_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `PUT /api/webui/rag-tests/{test_id}`

**Summary:** Update rag tests test id

Registered Flask endpoint `rag_tests.rag_tests_update` for `PUT /api/webui/rag-tests/{test_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_update_put`
- Flask endpoint: `rag_tests.rag_tests_update`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| test_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Rag Tests V2

#### `POST /api/webui/rag-tests-v2/run`

**Summary:** Create rag tests v2 run

Registered Flask endpoint `rag_tests.rag_tests_v2_run` for `POST /api/webui/rag-tests-v2/run`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_v2_run_post`
- Flask endpoint: `rag_tests.rag_tests_v2_run`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/rag-tests-v2/run/cancel/{job_id}`

**Summary:** Create rag tests v2 run cancel job id

Registered Flask endpoint `rag_tests.rag_tests_v2_run_cancel` for `POST /api/webui/rag-tests-v2/run/cancel/{job_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_v2_run_cancel_post`
- Flask endpoint: `rag_tests.rag_tests_v2_run_cancel`
- Request body: `application/json: GenericObject`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `GET /api/webui/rag-tests-v2/run/status/{job_id}`

**Summary:** Get rag tests v2 run status job id

Registered Flask endpoint `rag_tests.rag_tests_v2_run_status` for `GET /api/webui/rag-tests-v2/run/status/{job_id}`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `rag_tests_rag_tests_v2_run_status_get`
- Flask endpoint: `rag_tests.rag_tests_v2_run_status`
- Request body: `-`

Parameters:

| Name | In | Required | Schema |
|------|----|----------|--------|
| job_id | path | True | string |

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Rag Trigger Settings

#### `GET /api/webui/rag-trigger-settings`

**Summary:** Get rag trigger settings

Registered Flask endpoint `webui.get_rag_trigger_settings` for `GET /api/webui/rag-trigger-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_rag_trigger_settings_get`
- Flask endpoint: `webui.get_rag_trigger_settings`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/rag-trigger-settings`

**Summary:** Create rag trigger settings

Registered Flask endpoint `webui.update_rag_trigger_settings` for `POST /api/webui/rag-trigger-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_rag_trigger_settings_post`
- Flask endpoint: `webui.update_rag_trigger_settings`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Rag Trigger Test

#### `POST /api/webui/rag-trigger-test`

**Summary:** Create rag trigger test

Registered Flask endpoint `webui.rag_trigger_test` for `POST /api/webui/rag-trigger-test`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_rag_trigger_test_post`
- Flask endpoint: `webui.rag_trigger_test`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Ready

#### `GET /ready`

**Summary:** Readiness probe for ChironAI stack

Returns readiness for required runtime dependencies (Ollama provider and Qdrant).

- Operation ID: `ready_get`
- Flask endpoint: `ready`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Server

#### `POST /api/webui/server/stop`

**Summary:** Stop WebUI backend server

Requests a graceful shutdown of the local WebUI backend process.

- Operation ID: `webui_stop_server_post`
- Flask endpoint: `webui.stop_server`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Sessions

#### `GET /api/webui/sessions`

**Summary:** Create or resume CoreUI session

Returns a session id for browser-local CoreUI state. A supplied session_id query parameter is reused when valid.

- Operation ID: `webui_get_sessions_get`
- Flask endpoint: `webui.get_sessions`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

### Settings

#### `GET /api/webui/settings`

**Summary:** Get app settings

Returns persisted WebUI application settings plus active server port metadata.

- Operation ID: `webui_get_settings_get`
- Flask endpoint: `webui.get_settings`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Current WebUI settings. | application/json: AppSettingsResponse |

#### `POST /api/webui/settings`

**Summary:** Update app settings

Persists WebUI application settings. The response includes effective port metadata and restart hints.

- Operation ID: `webui_update_settings_post`
- Flask endpoint: `webui.update_settings`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Updated WebUI settings. | application/json: AppSettingsResponse |
| 400 | Bad request | application/json: ErrorResponse |

### Tester

#### `POST /api/webui/tester/chat`

**Summary:** Create tester chat

Registered Flask endpoint `webui.tester_chat` for `POST /api/webui/tester/chat`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_tester_chat_post`
- Flask endpoint: `webui.tester_chat`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

#### `POST /api/webui/tester/prompt-preview`

**Summary:** Create tester prompt preview

Registered Flask endpoint `webui.tester_prompt_preview` for `POST /api/webui/tester/prompt-preview`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_tester_prompt_preview_post`
- Flask endpoint: `webui.tester_prompt_preview`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Tester Settings

#### `GET /api/webui/tester-settings`

**Summary:** Get tester settings

Registered Flask endpoint `webui.get_tester_settings` for `GET /api/webui/tester-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_get_tester_settings_get`
- Flask endpoint: `webui.get_tester_settings`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

#### `POST /api/webui/tester-settings`

**Summary:** Create tester settings

Registered Flask endpoint `webui.update_tester_settings` for `POST /api/webui/tester-settings`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_update_tester_settings_post`
- Flask endpoint: `webui.update_tester_settings`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Testing

#### `POST /api/webui/testing/external-docs/preview`

**Summary:** Create testing external docs preview

Registered Flask endpoint `webui.testing_external_docs_preview` for `POST /api/webui/testing/external-docs/preview`. Payload shape is currently described generically until the route is promoted into core contracts.

- Operation ID: `webui_testing_external_docs_preview_post`
- Flask endpoint: `webui.testing_external_docs_preview`
- Request body: `application/json: GenericObject`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |
| 400 | Bad request | application/json: ErrorResponse |

### Version

#### `GET /api/webui/version`

**Summary:** Get application version

Returns the canonical ChironAI version, release stage, display name, and latest changelog entry used by CoreUI startup.

- Operation ID: `webui_get_version_get`
- Flask endpoint: `webui.get_version`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Current ChironAI version and latest changelog. | application/json: VersionResponse |

### root

#### `GET /`

**Summary:** Redirect to CoreUI

Redirects the bare HTTP root to the CoreUI application shell at /webui.

- Operation ID: `index_get`
- Flask endpoint: `index`
- Request body: `-`

Responses:

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | OK | application/json: GenericObject |

## Component Schemas

| Name | Type | Required Fields |
|------|------|-----------------|
| AppSettingsResponse | object | - |
| CoreUiNotification | object | - |
| DependenciesResponse | object | - |
| Dependency | object | - |
| DependencyJobResponse | object | - |
| DependencySource | object | - |
| DockerListResponse | object | - |
| DockerStatusResponse | object | - |
| ErrorResponse | object | - |
| ExtensionCapability | object | - |
| ExtensionCard | object | - |
| ExtensionDockerStatus | object | - |
| ExtensionRegistryResponse | object | - |
| ExtensionTab | object | - |
| ExtensionTabLoadState | object | - |
| ExtensionTabsResponse | object | - |
| GenericObject | object | - |
| InstalledExtension | object | - |
| InstalledExtensionsResponse | object | - |
| LlmProxyBuildRow | object | - |
| LlmProxyBuildsGetResponse | object | - |
| LlmProxyBuildsPutOkResponse | object | - |
| LlmProxyStatusResponse | object | - |
| ModelSettingsGetResponse | object | - |
| ModelSettingsPostResponse | object | - |
| ModelsListResponse | object | models |
| NotificationCreateRequest | object | session_id, source, title |
| NotificationCreateResponse | object | id |
| NotificationDismissRequest | object | session_id |
| NotificationDismissResponse | object | ok |
| NotificationsClearRequest | object | session_id |
| NotificationsClearResponse | object | deleted |
| NotificationsListResponse | object | notifications |
| OpenAiChatCompletionRequest | object | messages |
| OpenAiChatCompletionResponse | object | - |
| OpenAiModelListResponse | object | - |
| OpenAiModelResponse | object | - |
| ProviderModelEntry | object | - |
| RagCollectionsResponse | object | - |
| RagStatusResponse | object | - |
| StartupPerformanceResponse | object | - |
| VersionResponse | object | version, app_name, stage, display_name |
