# Validates the CloudFront soft-404 fix (issue #1251).
#
# Goal: a `terraform plan` must configure the frontend distribution so that a
# genuinely unknown path returns a real 404 rather than the app shell with a 200
# (the "soft 404" Google penalizes). Concretely:
#   - both the 403 and 404 custom error responses map to a real 404 served from
#     /404.html (NOT 200 /index.html);
#   - a viewer-request CloudFront function is attached to the default behavior so
#     allowlisted client-side routes can still be rewritten to /index.html;
#   - the function's allowlist logic (index.html fallback) is present in its code.
#
# Run with:  cd infra && terraform init -backend=false && terraform test
# (-backend=false skips the S3 backend so this stays offline / credential-free,
#  same as the other *.tftest.hcl files here — see monitoring.tftest.hcl.)

mock_provider "aws" {}
mock_provider "random" {}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"]
  }
}

override_data {
  target = data.aws_iam_policy_document.ecs_task_assume_role
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}
override_data {
  target = data.aws_iam_policy_document.secrets_read
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}
override_data {
  target = data.aws_iam_policy_document.ops_alerts
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}

variables {
  admin_api_key           = "a-sufficiently-long-admin-api-key-value-123"
  run_migrations_on_apply = false
}

# --- Unknown paths return a real 404, not a soft 200 ------------------------
run "unknown_paths_return_real_404" {
  command = plan

  # A private S3 origin behind OAC returns 403 for a missing object; it must be
  # mapped to a real 404 served from /404.html, never a 200 /index.html.
  assert {
    condition = length([
      for r in aws_cloudfront_distribution.frontend.custom_error_response :
      r if r.error_code == 403 && r.response_code == 404 && r.response_page_path == "/404.html"
    ]) == 1
    error_message = "403 (missing S3 object) must map to a real 404 served from /404.html."
  }

  assert {
    condition = length([
      for r in aws_cloudfront_distribution.frontend.custom_error_response :
      r if r.error_code == 404 && r.response_code == 404 && r.response_page_path == "/404.html"
    ]) == 1
    error_message = "404 must map to a real 404 served from /404.html."
  }

  # Regression guard: NO custom error response may still soft-404 to 200/index.html.
  assert {
    condition = length([
      for r in aws_cloudfront_distribution.frontend.custom_error_response :
      r if r.response_code == 200
    ]) == 0
    error_message = "No custom error response may return 200 (that reintroduces the soft 404)."
  }
}

# --- A viewer-request function distinguishes SPA routes from unknown paths ---
run "spa_router_function_attached" {
  command = plan

  assert {
    condition     = aws_cloudfront_function.spa_router.runtime == "cloudfront-js-2.0"
    error_message = "The SPA-router function must target the cloudfront-js-2.0 runtime."
  }

  # The function must still be able to serve the app shell for real client-side
  # routes; the allowlist rewrites those to /index.html.
  assert {
    condition     = can(regex("/index.html", aws_cloudfront_function.spa_router.code))
    error_message = "The SPA-router function must rewrite allowlisted routes to /index.html."
  }

  # Exactly one viewer-request function is wired onto the default behavior.
  assert {
    condition = length([
      for f in aws_cloudfront_distribution.frontend.default_cache_behavior[0].function_association :
      f if f.event_type == "viewer-request"
    ]) == 1
    error_message = "A viewer-request function must be associated with the default cache behavior."
  }
}
