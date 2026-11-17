<?php
/**
 * One-time, authenticated ESC Table home_04–home_08 conversion.
 * Temporarily uploaded by CI, removed after the request. No public REST write route.
 */
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    http_response_code(404);
    exit;
}
$token = (string) ($_SERVER['HTTP_X_ESC_HOME_CATALOG_TOKEN'] ?? '');
if ($token === '' || !hash_equals('__AUTH_TOKEN_SHA256__', hash('sha256', $token))) {
    http_response_code(404);
    exit;
}
unset($token);
require __DIR__ . '/wp-load.php';

function esc_catalog_response(int $status, array $payload): void {
    http_response_code($status);
    echo wp_json_encode($payload);
    exit;
}

if (!class_exists('TablePress') || !isset(TablePress::$model_table)) {
    esc_catalog_response(500, ['ok' => false, 'reason' => 'ESC Table plugin not loaded']);
}

$categories = [
    'home_04' => 'non-bao-hiem-nua-dau',
    'home_05' => 'non-bao-hiem-boc-da',
    'home_06' => 'non-bao-hiem-co-kinh',
    'home_07' => 'non-bao-hiem-3-4',
    'home_08' => 'mau-non-khac',
];
$base = '/wp-json/wp/v2/product?';
$common = '&product_lang=vi&status=publish&per_page=8&orderby=date&order=desc';
$fieldFilter = '&_fields=id,title,slug,featured_media_url,date';
$headers = ['api-key', 'note', 'api-name', 'api-slug', 'api-img'];
$row = ['auto', '', 'title.rendered', 'slug', 'featured_media_url'];
$blankLabels = ['', '', '', '', ''];
$staging = [];

foreach ($categories as $id => $slug) {
    $target = $base . 'product_cat_slug=' . $slug . $common . $fieldFilter;
    $table = TablePress::$model_table->load($id);
    $metaKey = 'tablepress_meta_' . $id;
    $meta = get_option($metaKey, []);
    if (is_wp_error($table) || !is_array($table) || ($table['id'] ?? '') !== $id || !is_array($meta)) {
        esc_catalog_response(409, ['ok'=>false,'reason'=>'Invalid table or metadata','table'=>$id]);
    }
    $oldAPI = (string) ($meta['api'] ?? '');
    $already = $oldAPI === $target &&
        count($table['data'] ?? []) === 3 &&
        ($table['data'][0] ?? []) === $headers &&
        ($table['data'][2] ?? []) === $row;
    $allowedPrior = $id === 'home_04'
        ? ($base . 'product_cat_slug=' . $slug . $common)
        : 'Product';
    if (!$already && $oldAPI !== $allowedPrior) {
        esc_catalog_response(409, ['ok'=>false,'reason'=>'Unexpected ESC Table source','table'=>$id]);
    }
    if (!$already && $id !== 'home_04' &&
        (!is_array($table['data'] ?? null) ||
         count($table['data']) < 3 ||
         ($table['data'][0][0] ?? '') !== 'key')) {
        esc_catalog_response(409, ['ok'=>false,'reason'=>'Unexpected legacy columns','table'=>$id]);
    }
    if (!$already && $id === 'home_04' &&
        (($table['data'][0] ?? []) !== $headers || ($table['data'][2] ?? []) !== $row)) {
        esc_catalog_response(409, ['ok'=>false,'reason'=>'home_04 template changed','table'=>$id]);
    }

    // A permanent server-side recovery snapshot is made before every mutation.
    $backupKey = 'esc_catalog_' . $id . '_backup_before_api_20261117';
    if (!$already && get_option($backupKey, false) === false) {
        $saved = add_option($backupKey, [
            'table' => $table,
            'meta' => $meta,
            'saved_gmt' => gmdate('c'),
        ], '', false);
        if (!$saved) {
            esc_catalog_response(500, ['ok'=>false,'reason'=>'Cannot save backup','table'=>$id]);
        }
    }
    $staging[$id] = compact('table', 'meta', 'metaKey', 'target', 'already', 'backupKey');
}

// Preflight all five tables before writing any. Changes are idempotent.
$report = [];
foreach ($staging as $id => $item) {
    $table = $item['table'];
    $meta = $item['meta'];
    if (!$item['already']) {
        $meta['api'] = $item['target'];
        update_option($item['metaKey'], $meta, false);
        if ($id !== 'home_04') {
            $table['data'] = [$headers, $blankLabels, $row];
            $res = TablePress::$model_table->save($table);
            if (is_wp_error($res) || $res !== $id) {
                esc_catalog_response(500, ['ok'=>false,'reason'=>'Cannot save table; recovery snapshot available','table'=>$id]);
            }
        }
    }

    $verify = TablePress::$model_table->load($id);
    $verifyMeta = get_option($item['metaKey'], []);
    if (is_wp_error($verify) || !is_array($verify) || !is_array($verifyMeta) ||
        ($verifyMeta['api'] ?? '') !== $item['target'] ||
        count($verify['data'] ?? []) !== 3 ||
        ($verify['data'][0] ?? []) !== $headers ||
        ($verify['data'][2] ?? []) !== $row) {
        esc_catalog_response(500, ['ok'=>false,'reason'=>'Verification mismatch; recovery snapshot available','table'=>$id]);
    }
    $report[$id] = ['changed'=>!$item['already'],'api'=>$item['target'],'items'=>1];
}
esc_catalog_response(200, ['ok'=>true,'sections'=>$report]);
