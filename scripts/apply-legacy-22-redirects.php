<?php
/**
 * Temporary one-time Blue Sea legacy 301 installer.
 * Uploaded only by the authenticated GitHub Actions FTP workflow.
 * Reuses the WordPress "Điều hướng URL" CPT, not Astro hard-code.
 * The caller injects unpredictable token + base64 JSON at runtime.
 */
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST' ||
    !hash_equals('__ESC_TOKEN_PLACEHOLDER__', (string) ($_SERVER['HTTP_X_ESC_LEGACY_AUTH'] ?? ''))) {
    http_response_code(403);
    echo json_encode(['ok' => false, 'error' => 'forbidden']);
    exit;
}
register_shutdown_function(static function (): void { @unlink(__FILE__); });

try {
    $manifest = json_decode((string) base64_decode('__ESC_MAPPING_BASE64__', true), true);
    if (!is_array($manifest) || !isset($manifest['rules']) || !is_array($manifest['rules']) ||
        count($manifest['rules']) !== 22) {
        throw new RuntimeException('Expected exact 22-route manifest');
    }
    require __DIR__ . '/wp-load.php';
    if (!post_type_exists('chuyen-huong-link') ||
        !function_exists('esc_url_routing_update_field') ||
        !function_exists('esc_url_routing_seed_insert_post') ||
        !function_exists('esc_url_routing_seed_write_logs')) {
        throw new RuntimeException('ESC URL routing manager is not loaded');
    }
    $rows = [];
    $fromSet = [];
    foreach ($manifest['rules'] as $rule) {
        $from = (string) ($rule['from'] ?? '');
        $to = (string) ($rule['to'] ?? '');
        if (!preg_match('~^/[a-z0-9][a-z0-9/_-]*(?:\\.html)?/?$~D', $from) ||
            !preg_match('~^/[a-z0-9][a-z0-9/_-]*/?$~D', $to) ||
            $from === $to || (int) ($rule['type'] ?? 0) !== 301 ||
            ($rule['matchType'] ?? '') !== 'Exact' ||
            isset($fromSet[rtrim($from, '/')])) {
            throw new RuntimeException('Invalid/duplicated manifest route ' . $from);
        }
        $fromSet[rtrim($from, '/')] = true;
        $rows[] = ['from' => $from, 'to' => $to];
    }

    // Preflight ALL existing routes first; reject collisions rather than overwrite
    // any user-created rule/conditional Rewrite. No writes on a conflict.
    $existing = [];
    $ids = get_posts([
        'post_type' => 'chuyen-huong-link',
        'post_status' => ['publish', 'draft', 'private', 'pending'],
        'posts_per_page' => -1,
        'fields' => 'ids',
        'no_found_rows' => true,
    ]);
    foreach ($ids as $postId) {
        $old = (string) get_post_meta((int) $postId, 'from_link', true);
        if ($old === '' || strcasecmp((string) get_post_meta((int) $postId, 'match_type', true), 'Exact') !== 0) {
            continue;
        }
        $normalized = rtrim($old, '/') ?: '/';
        if (!isset($fromSet[$normalized])) continue;
        if (isset($existing[$normalized])) {
            throw new RuntimeException('Duplicate existing WordPress route for ' . $normalized);
        }
        $existing[$normalized] = (int) $postId;
    }
    foreach ($rows as $row) {
        $key = rtrim($row['from'], '/');
        if (!isset($existing[$key])) continue;
        $id = $existing[$key];
        $oldTarget = (string) get_post_meta($id, 'to_link', true);
        $oldType = (string) get_post_meta($id, 'type', true);
        if ($oldTarget !== $row['to'] || $oldType !== '301' ||
            get_post_status($id) !== 'publish') {
            throw new RuntimeException('Existing conflicting route ' . $key . ' (ID ' . $id . ')');
        }
    }

    $created = 0; $unchanged = 0; $logs = []; $result = [];
    foreach ($rows as $row) {
        $key = rtrim($row['from'], '/');
        $id = $existing[$key] ?? 0;
        if ($id > 0 && (int) get_post_meta($id, 'enable', true) === 1) {
            $unchanged++;
        } elseif ($id > 0) {
            esc_url_routing_update_field($id, 'enable', 1);
            $logs[] = $id;
        } else {
            $seedKey = 'legacy22-' . substr(hash('sha256', $row['from']), 0, 18);
            $id = esc_url_routing_seed_insert_post($seedKey, 'Legacy 301 ' . $row['from']);
            if ($id <= 0) throw new RuntimeException('Unable to create ' . $row['from']);
            esc_url_routing_update_field($id, 'from_link', $row['from']);
            esc_url_routing_update_field($id, 'to_link', $row['to']);
            esc_url_routing_update_field($id, 'type', '301');
            esc_url_routing_update_field($id, 'match_type', 'Exact');
            esc_url_routing_update_field($id, 'enable', 1);
            update_post_meta($id, '_esc_route_priority', 80);
            update_post_meta($id, '_esc_route_conditions', []);
            update_post_meta($id, '_esc_legacy_301_manifest', (string) $manifest['version']);
            $logs[] = $id;
            $created++;
        }
        clean_post_cache($id);
        $result[] = ['id' => $id, 'from' => $row['from'], 'to' => $row['to']];
    }
    // The existing Astro incremental redirect loader consumes this event log.
    esc_url_routing_seed_write_logs($logs, 'modify');
    if (count($result) !== 22) throw new RuntimeException('Result count does not match manifest');
    echo wp_json_encode([
        'ok' => true, 'created' => $created, 'unchanged' => $unchanged,
        'rules' => $result, 'manifest_version' => $manifest['version'],
    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => $e->getMessage()], JSON_UNESCAPED_UNICODE);
}
