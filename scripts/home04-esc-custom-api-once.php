<?php
/**
 * One-use migration for the existing Blue Sea ESC Table home_04.
 * This file is shipped temporarily into the WordPress root by GitHub Actions
 * and must be removed after the authenticated one-time POST completes.
 */
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(404);
    exit;
}
$token = (string) ($_SERVER['HTTP_X_ESC_HOME04_TOKEN'] ?? '');
if (!$token || !hash_equals('__AUTH_TOKEN_SHA256__', hash('sha256', $token))) {
    http_response_code(404);
    exit;
}
unset($token);
require __DIR__ . '/wp-load.php';

function esc_home04_response(int $status, array $payload): void {
    http_response_code($status);
    echo wp_json_encode($payload);
    exit;
}

$source = 'Product';
$target = '/wp-json/wp/v2/product?product_cat_slug=non-bao-hiem-nua-dau&product_lang=vi&status=publish&per_page=8&orderby=date&order=desc';
$backupKey = 'esc_home04_backup_before_custom_api_20261117';
$metaKey = 'tablepress_meta_home_04';
$id = 'home_04';

if (!class_exists('TablePress') || !isset(TablePress::$model_table)) {
    esc_home04_response(500, ['ok'=>false, 'error'=>'ESC Table plugin not loaded']);
}
$table = TablePress::$model_table->load($id);
if (is_wp_error($table) || !is_array($table) || ($table['id'] ?? '') !== $id) {
    esc_home04_response(500, ['ok'=>false, 'error'=>'ESC Table home_04 missing or invalid']);
}
$meta = get_option($metaKey, []);
if (!is_array($meta)) {
    esc_home04_response(500, ['ok'=>false, 'error'=>'ESC Table source meta invalid']);
}
$oldSource = (string) ($meta['api'] ?? '');
if ($oldSource !== $source && $oldSource !== $target) {
    esc_home04_response(409, ['ok'=>false, 'error'=>'ESC Table was edited concurrently; no changes made']);
}

$expectedHeaders = ['api-key','note','api-name','api-slug','api-img'];
$expectedRow = ['auto','','title.rendered','slug','featured_media_url'];
$complete = (
    $oldSource === $target &&
    count($table['data'] ?? []) === 3 &&
    ($table['data'][0] ?? []) === $expectedHeaders &&
    ($table['data'][2] ?? []) === $expectedRow
);
if ($complete) {
    esc_home04_response(200, ['ok'=>true, 'changed'=>false, 'table_id'=>$id, 'api'=>$target, 'items'=>1]);
}
if ($oldSource !== $source) {
    esc_home04_response(409, ['ok'=>false, 'error'=>'Existing custom API rows differ; no changes made']);
}
if (!is_array($table['data'] ?? null) ||
    count($table['data']) < 3 ||
    ($table['data'][0][0] ?? '') !== 'key') {
    esc_home04_response(409, ['ok'=>false, 'error'=>'Unexpected old ESC Table structure; no changes made']);
}

// Preserve the complete pre-migration table including options, visibility,
// original fixed product rows, preview image and other custom metadata.
if (get_option($backupKey, false) === false) {
    $backupCreated = add_option($backupKey, [
        'table' => $table,
        'meta' => $meta,
        'snapshot_gmt' => gmdate('c'),
    ], '', false);
    if (!$backupCreated) {
        esc_home04_response(500, ['ok'=>false, 'error'=>'Backup creation failed']);
    }
}

$updatedMeta = $meta;
$updatedMeta['api'] = $target;
update_option($metaKey, $updatedMeta, false);
$table['data'] = [
    $expectedHeaders,
    ['','','','',''],
    $expectedRow,
];
$result = TablePress::$model_table->save($table);
if (is_wp_error($result) || $result !== $id) {
    update_option($metaKey, $meta, false);
    esc_home04_response(500, ['ok'=>false, 'error'=>'Saving ESC Table failed; source meta rolled back']);
}

$verify = TablePress::$model_table->load($id);
$verifyMeta = get_option($metaKey, []);
if (is_wp_error($verify) || !is_array($verify) || !is_array($verifyMeta) ||
    ($verifyMeta['api'] ?? '') !== $target ||
    ($verify['data'][0] ?? []) !== $expectedHeaders ||
    ($verify['data'][2] ?? []) !== $expectedRow ||
    count($verify['data'] ?? []) !== 3) {
    esc_home04_response(500, ['ok'=>false, 'error'=>'Post-save verification mismatch']);
}
esc_home04_response(200, [
    'ok' => true,
    'changed' => true,
    'table_id' => $id,
    'api' => $target,
    'items' => 1,
    'backup' => $backupKey,
]);
