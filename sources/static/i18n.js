const i18n = {
    uk: {
        // dashboard
        edit:                'Редагувати',
        section_title:       'Моніторинг цін',
        col_product:         'Товар',
        col_date:            'Дата',
        col_count:           'К-сть',
        col_purchased:       'Ціна купівлі',
        col_price_uah:       'Ціна, ₴',
        col_purchased_total: 'Сума купівлі',
        col_total:           'Сума, ₴',
        col_change:          'Зміна, ₴',
        col_trend:           'Динаміка (60 днів)',
        col_links:           'Посилання',
        total_row:           n => `Разом (${n} позицій)`,
        cache_meta:          (min, ts) => `кеш ${min} хв · оновлено ${ts}`,
        link_chart:          'Графік',
        // landing
        landing_title:    'Моніторинг цін з Hotline.ua',
        landing_desc:     'Додай список товарів — отримай зведену таблицю з поточними цінами, динамікою та порівнянням з ціною купівлі. Твоя таблиця зберігається за унікальним посиланням.',
        new_table:        'Нова таблиця',
        import_yaml:      'Імпортувати YAML',
        my_tables:        'Мої таблиці',
        remove:           'Видалити',
        confirm_delete:   'Видалити цю таблицю назавжди?',
        logout:           'Вийти',
        // editor
        to_table:             'До таблиці',
        section_products:     'Список товарів',
        section_share:        'Посилання на таблицю',
        share_hint:           'Збережи це посилання — воно відкриває твою таблицю:',
        add_product:          '+ Додати товар',
        save:                 'Зберегти',
        export_yaml:          'Завантажити YAML',
        copy_url:             'Скопіювати',
        label_url:            'URL товару на Hotline',
        label_title:          'Назва (опціонально)',
        label_purchase_price: 'Ціна купівлі, ₴',
        label_purchase_date:  'Дата купівлі',
        placeholder_title:    'Назва товару',
        save_error:           'Помилка збереження: ',
        // chart
        back:             'Назад',
    },
    en: {
        edit:                'Edit',
        section_title:       'Price Monitor',
        col_product:         'Product',
        col_date:            'Date',
        col_count:           'Qty',
        col_purchased:       'Buy price',
        col_price_uah:       'Price, ₴',
        col_purchased_total: 'Buy total',
        col_total:           'Total, ₴',
        col_change:          'Change, ₴',
        col_trend:           'Trend (60 days)',
        col_links:           'Links',
        total_row:           n => `Total (${n} items)`,
        cache_meta:          (min, ts) => `cache ${min} min · updated ${ts}`,
        link_chart:          'Chart',
        landing_title:    'Price Monitoring from Hotline.ua',
        landing_desc:     'Add a product list — get a summary table with current prices, trends and comparison to your purchase price. Your table is saved at a unique link.',
        new_table:        'New table',
        import_yaml:      'Import YAML',
        my_tables:        'My tables',
        remove:           'Remove',
        confirm_delete:   'Delete this table permanently?',
        logout:           'Log out',
        to_table:             'Back to table',
        section_products:     'Product list',
        section_share:        'Table link',
        share_hint:           'Save this link — it opens your table:',
        add_product:          '+ Add product',
        save:                 'Save',
        export_yaml:          'Download YAML',
        copy_url:             'Copy',
        back:                 'Back',
        label_url:            'Product URL on Hotline',
        label_title:          'Name (optional)',
        label_purchase_price: 'Buy price, ₴',
        label_purchase_date:  'Buy date',
        placeholder_title:    'Product name',
        save_error:           'Save error: ',
    },
    ru: {
        edit:                'Редактировать',
        section_title:       'Мониторинг цен',
        col_product:         'Товар',
        col_date:            'Дата',
        col_count:           'Кол-во',
        col_purchased:       'Цена покупки',
        col_price_uah:       'Цена, ₴',
        col_purchased_total: 'Сумма покупки',
        col_total:           'Сумма, ₴',
        col_change:          'Изменение, ₴',
        col_trend:           'Динамика (60 дней)',
        col_links:           'Ссылки',
        total_row:           n => `Итого (${n} позиций)`,
        cache_meta:          (min, ts) => `кеш ${min} мин · обновлено ${ts}`,
        link_chart:          'График',
        landing_title:    'Мониторинг цен с Hotline.ua',
        landing_desc:     'Добавь список товаров — получи сводную таблицу с текущими ценами, динамикой и сравнением с ценой покупки. Твоя таблица хранится по уникальной ссылке.',
        new_table:        'Новая таблица',
        import_yaml:      'Импортировать YAML',
        my_tables:        'Мои таблицы',
        remove:           'Удалить',
        confirm_delete:   'Удалить эту таблицу навсегда?',
        logout:           'Выйти',
        to_table:             'К таблице',
        section_products:     'Список товаров',
        section_share:        'Ссылка на таблицу',
        share_hint:           'Сохрани эту ссылку — она открывает твою таблицу:',
        add_product:          '+ Добавить товар',
        save:                 'Сохранить',
        export_yaml:          'Скачать YAML',
        copy_url:             'Скопировать',
        back:                 'Назад',
        label_url:            'URL товара на Hotline',
        label_title:          'Название (необязательно)',
        label_purchase_price: 'Цена покупки, ₴',
        label_purchase_date:  'Дата покупки',
        placeholder_title:    'Название товара',
        save_error:           'Ошибка сохранения: ',
    },
};

let currentLang = 'uk';

function t(key) {
    return i18n[currentLang][key] ?? key;
}

function applyLang(lang) {
    currentLang = lang;
    const tr = i18n[lang];
    document.documentElement.lang = lang;

    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = tr[el.dataset.i18n] ?? el.textContent;
    });

    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        el.title = tr[el.dataset.i18nTitle] ?? el.title;
    });

    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = tr[el.dataset.i18nPlaceholder] ?? el.placeholder;
    });

    const totalEl = document.querySelector('[data-i18n-total]');
    if (totalEl) totalEl.textContent = tr.total_row(totalEl.dataset.count);

    const metaEl = document.querySelector('[data-i18n-meta]');
    if (metaEl) metaEl.textContent = tr.cache_meta(metaEl.dataset.ttl, metaEl.dataset.ts);

    if (typeof onLangChange === 'function') onLangChange(lang);

    const sel = document.getElementById('lang-select');
    if (sel) sel.value = lang;
}

function setLang(lang) {
    localStorage.setItem('lang', lang);
    applyLang(lang);
}

function detectLang() {
    const supported = ['uk', 'en', 'ru'];
    for (const locale of (navigator.languages || [navigator.language])) {
        const tag = locale.split('-')[0].toLowerCase();
        if (supported.includes(tag)) return tag;
    }
    return 'uk';
}

(function init() {
    const lang = localStorage.getItem('lang') || detectLang();
    applyLang(lang);
})();
