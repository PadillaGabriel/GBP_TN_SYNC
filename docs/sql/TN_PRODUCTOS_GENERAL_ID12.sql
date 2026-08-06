SELECT
    i.item_id AS item_id,
    LTRIM(RTRIM(ISNULL(i.item_code, ''))) AS item_code,
    LTRIM(RTRIM(ISNULL(i.item_vendorCode, ''))) AS item_vendorCode,
    LTRIM(RTRIM(ISNULL(i.item_codeAlternative, ''))) AS item_codeAlternative,
    LTRIM(RTRIM(ISNULL(i.item_desc, ''))) AS item_desc,

    CONVERT(
        BIT,
        CASE
            WHEN ISNULL(i.item_disabled, 0) = 0
             AND ISNULL(i.item_not4Sale, 0) = 0
            THEN 1
            ELSE 0
        END
    ) AS item_active,

    CONVERT(BIT, ISNULL(i.item_web, 0)) AS item_web,
    CONVERT(BIT, ISNULL(i.item_disabled, 0)) AS item_disabled,
    CONVERT(BIT, ISNULL(i.item_not4Sale, 0)) AS item_not_for_sale,
    CONVERT(BIT, ISNULL(i.item_isForAssociation, 0)) AS item_isForAssociation,

    CONVERT(
        DECIMAL(19, 3),
        CASE
            WHEN ISNULL(i.item_weight, 0) > 0
            THEN i.item_weight / 1000.0
            ELSE 0
        END
    ) AS peso,

    CONVERT(DECIMAL(19, 2), ISNULL(i.item_higth, 0)) AS alto,
    CONVERT(DECIMAL(19, 2), ISNULL(i.item_wide, 0)) AS ancho,
    CONVERT(DECIMAL(19, 2), ISNULL(i.item_large, 0)) AS profundidad,

    COALESCE(
        NULLIF(LTRIM(RTRIM(i.item_web_title)), ''),
        NULLIF(LTRIM(RTRIM(i.item_WebSite_desc)), ''),
        NULLIF(LTRIM(RTRIM(i.item_desc)), ''),
        ''
    ) AS descripcion_corta,

    COALESCE(
        NULLIF(LTRIM(RTRIM(i.item_descHTML)), ''),
        NULLIF(LTRIM(RTRIM(i.item_descHTMLStripped)), ''),
        NULLIF(LTRIM(RTRIM(i.item_WebSite_desc)), ''),
        NULLIF(LTRIM(RTRIM(i.item_desc)), ''),
        ''
    ) AS descripcion_larga,

    LTRIM(RTRIM(ISNULL(b.brand_desc, ''))) AS brand_name,
    LTRIM(RTRIM(ISNULL(c.cat_desc, ''))) AS category_name,
    LTRIM(RTRIM(ISNULL(sc.subcat_desc, ''))) AS subcategory_name,

    STUFF(
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image1, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image1)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image2, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image2)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image3, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image3)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image4, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image4)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image5, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image5)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image6, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image6)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image7, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image7)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image8, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image8)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image9, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image9)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END
        +
        CASE
            WHEN NULLIF(LTRIM(RTRIM(ISNULL(i.item_WebSite_url4Image10, ''))), '') IS NOT NULL
            THEN '|' + REPLACE(
                LTRIM(RTRIM(i.item_WebSite_url4Image10)),
                'http://http2.mlstatic.com/',
                'https://http2.mlstatic.com/'
            )
            ELSE ''
        END,
        1,
        1,
        ''
    ) AS imagenes_urls

FROM dbo.tbItem AS i

LEFT JOIN dbo.tbBrand AS b
    ON b.comp_id = i.comp_id
   AND b.brand_id = i.brand_id

LEFT JOIN dbo.tbCategory AS c
    ON c.comp_id = i.comp_id
   AND c.cat_id = i.cat_id

LEFT JOIN dbo.tbSubCategory AS sc
    ON sc.comp_id = i.comp_id
   AND sc.cat_id = i.cat_id
   AND sc.subcat_id = i.subcat_id

WHERE i.comp_id = 1
