# Aggregation showcase

_Generated 2026-10-09 08:25 UTC by `backend/scripts/gen_aggregation_showcase.py` against MongoDB 8.0.28 with the demo seed 55 events, 400 saved_events, 3000 event_interactions, 20 posts, 120 comments, 300 reactions.
Every pipeline below is imported from the code that serves the API (not retyped), and every `explain` block was captured from the server._

**How to read the explain tables.** `totalKeysExamined` = index entries read; `totalDocsExamined` = documents fetched; `nReturned` = documents the query planner hands to the rest of the pipeline. A healthy indexed query reads few keys/docs relative to the collection size (the numbers above give the sizes). With only a few dozen events the planner's wall-clock times are ~1 ms either way, so the *keys/docs examined* columns are the meaningful evidence, not milliseconds.

**Honest caveats.** (1) Stages after the first `$match`/`$sort`/`$limit` (`$lookup`, `$facet`, `$group`, `$setWindowFields`, `$addFields`) run on the matched documents in memory and are not index-served; the explain shows the index-served prefix. (2) Where a sort includes `_id` as a deterministic tiebreak, the index provides the filter but MongoDB adds an in-memory `SORT` limited by `$limit`. (3) A `$lookup` sub-pipeline is explained separately below because the parent explain does not expand it.

## Index inventory

| Collection | Index | Kind | Used by |
|---|---|---|---|
| `users` | `email_unique` `{"email": 1}` | unique | login, registration |
| `users` | `followed_clubs_multikey` `{"followed_club_ids": 1}` | multikey | club follower counts |
| `clubs` | `slug_unique` `{"slug": 1}` | unique | club by slug |
| `clubs` | `admin_ids_multikey` `{"admin_ids": 1}` | multikey | authorization (is this user an admin of the club?) |
| `clubs` | `verified` `{"verified": 1}` | compound/single | verified-club list (tiny collection) |
| `events` | `status_start` `{"status": 1, "schedule.start": 1}` | compound/single | catalogue, home ranges, Top 10, Suggested, analytics |
| `events` | `club_start` `{"club_id": 1, "schedule.start": 1}` | compound/single | club event lists |
| `events` | `category_start` `{"category": 1, "schedule.start": 1}` | compound/single | created per spec; the planner currently prefers `status_start` for the catalogue (see entry 1), so treat it as a candidate for dropping if write cost matters |
| `events` | `tags_multikey` `{"tags": 1}` | multikey | tag lookups (multikey) |
| `events` | `featured_partial` `{"featured.featured_at": -1}` | partial | Featured section |
| `events` | `events_text` `{"_fts": "text", "_ftsx": 1}` | text, weights {"club_snapshot.name": 5, "description": 1, "one_liner": 3, "tags": 6, "title": 10, "venue.name": 2} | catalogue `q=` search |
| `saved_events` | `user_event_unique` `{"user_id": 1, "event_id": 1}` | unique | idempotent save |
| `saved_events` | `user_event_start` `{"user_id": 1, "event_start": 1}` | compound/single | saved list, calendar |
| `event_interactions` | `event_type_ts` `{"event_id": 1, "type": 1, "ts": 1}` | compound/single | Top 10 `$lookup` (entry 4) |
| `event_interactions` | `ts_ttl` `{"ts": 1}` | TTL 90d | auto-expiry after 90 days; also the time-window range for the funnel (entry 18) |
| `posts` | `scope_created` `{"scope.type": 1, "scope.ref_id": 1, "created_at": -1}` | compound/single | community feeds |
| `posts` | `posts_text` `{"_fts": "text", "_ftsx": 1}` | text, weights {"body": 1, "title": 1} | post search |
| `comments` | `post_created` `{"post_id": 1, "created_at": 1}` | compound/single | comment threads |
| `comments` | `parent` `{"parent_id": 1}` | compound/single | reply `$lookup` (foreignField `parent_id`) |
| `reactions` | `user_target_unique` `{"user_id": 1, "target_type": 1, "target_id": 1}` | unique | one reaction per user per target |

## Aggregation pipelines

### 1. Catalogue: filters + facets in one round trip

**Endpoint:** `GET /events?category=technical&category=hackathon&club=acm&club=ieee`  
**Collection:** `events`  
**MongoDB features:** `$match` (OR within a group via `$in`, AND between groups), `$facet` (items + total + 2 disjunctive facets), `$group`, `$sort`, `$skip/$limit`

**Purpose.** Returns one page of event cards, the exact total, and per-category / per-club counts for the current filters, all from a single scan of the public-and-upcoming set. This is what a SQL application would do with 4 queries.

_Parameters used here:_ categories technical+hackathon, clubs ACM+IEEE

<details><summary>Pipeline (2 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published",
      "cancelled_at": null,
      "schedule.end": {
        "$gte": {
          "$date": "2026-10-09T08:25:04.955Z"
        }
      }
    }
  },
  {
    "$facet": {
      "items": [
        {
          "$match": {
            "category": {
              "$in": [
                "technical",
                "hackathon"
              ]
            },
            "club_id": {
              "$in": [
                {
                  "$oid": "6ac8a4d1ae2f822d6c0686b6"
                },
                {
                  "$oid": "6ac8a4d1ae2f822d6c0686b8"
                }
              ]
            }
          }
        },
        {
          "$addFields": {
            "popularity": {
              "$add": [
                {
                  "$multiply": [
                    {
                      "$ifNull": [
                        "$stats.saves",
                        0
                      ]
                    },
                    3
                  ]
                },
                {
                  "$multiply": [
                    {
                      "$ifNull": [
                        "$stats.registration_clicks",
                        0
                      ]
                    },
                    2
                  ]
                },
                {
                  "$ifNull": [
                    "$stats.views",
                    0
                  ]
                }
              ]
            }
          }
        },
        {
          "$sort": {
            "schedule.start": 1,
            "_id": 1
          }
        },
        {
          "$skip": 0
        },
        {
          "$limit": 20
        },
        {
          "$addFields": {
            "registration_open": {
              "$and": [
                {
                  "$eq": [
                    "$registration.required",
                    true
                  ]
                },
                {
                  "$or": [
                    {
                      "$eq": [
                        {
                          "$ifNull": [
                            "$registration.deadline",
                            null
                          ]
                        },
                        null
                      ]
                    },
                    {
                      "$gt": [
                        "$registration.deadline",
                        {
                          "$date": "2026-10-09T08:25:04.955Z"
                        }
                      ]
                    }
                  ]
                },
                {
                  "$gt": [
                    "$schedule.start",
                    {
                      "$date": "2026-10-09T08:25:04.955Z"
                    }
                  ]
                }
              ]
            }
          }
        },
        {
          "$project": {
            "description": 0,
            "details": 0,
            "contact": 0,
            "change_log": 0
          }
        },
        {
          "$project": {
            "popularity": 0,
            "_text_score": 0
          }
        }
      ],
      "total": [
        {
          "$match": {
            "category": {
              "$in": [
                "technical",
                "hackathon"
              ]
            },
            "club_id": {
              "$in": [
                {
                  "$oid": "6ac8a4d1ae2f822d6c0686b6"
                },
                {
                  "$oid": "6ac8a4d1ae2f822d6c0686b8"
                }
              ]
            }
          }
        },
        {
          "$count": "n"
        }
      ],
      "by_category": [
        {
          "$match": {
            "club_id": {
              "$in": [
                {
                  "$oid": "6ac8a4d1ae2f822d6c0686b6"
                },
                {
                  "$oid": "6ac8a4d1ae2f822d6c0686b8"
                }
              ]
            }
          }
        },
        {
          "$group": {
            "_id": "$category",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "count": -1,
            "_id": 1
          }
        }
      ],
      "by_club": [
        {
          "$match": {
            "category": {
              "$in": [
                "technical",
                "hackathon"
              ]
            }
          }
        },
        {
          "$group": {
            "_id": "$club_id",
            "name": {
              "$first": "$club_snapshot.name"
            },
            "slug": {
              "$first": "$club_snapshot.slug"
            },
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "count": -1,
            "name": 1
          }
        }
      ]
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `FETCH > IXSCAN(status_start)` |
|---|---|
| Index | **index scan** on `status_start` |
| nReturned | 37 |
| totalKeysExamined | 45 |
| totalDocsExamined | 45 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

The base `$match` (`status`, `schedule.end`) is index-served; the `$facet` branches operate on those documents in memory.

### 2. Weighted full-text search

**Endpoint:** `GET /events?q=cloud`  
**Collection:** `events`  
**MongoDB features:** `$text` with a weighted text index (title 10, tags 6, club name 5, one_liner 3, venue 2, description 1), `$meta: textScore`, `$facet`

**Purpose.** Relevance-ranked search: a hit in the title outranks the same hit in the description. `$text` must be the first stage, so visibility filters ride in the same `$match`.

_Parameters used here:_ q="cloud"

<details><summary>Pipeline (3 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published",
      "cancelled_at": null,
      "schedule.end": {
        "$gte": {
          "$date": "2026-10-09T08:25:04.955Z"
        }
      },
      "$text": {
        "$search": "cloud"
      }
    }
  },
  {
    "$addFields": {
      "_text_score": {
        "$meta": "textScore"
      }
    }
  },
  {
    "$facet": {
      "items": [
        {
          "$addFields": {
            "popularity": {
              "$add": [
                {
                  "$multiply": [
                    {
                      "$ifNull": [
                        "$stats.saves",
                        0
                      ]
                    },
                    3
                  ]
                },
                {
                  "$multiply": [
                    {
                      "$ifNull": [
                        "$stats.registration_clicks",
                        0
                      ]
                    },
                    2
                  ]
                },
                {
                  "$ifNull": [
                    "$stats.views",
                    0
                  ]
                }
              ]
            }
          }
        },
        {
          "$sort": {
            "_text_score": -1,
            "schedule.start": 1,
            "_id": 1
          }
        },
        {
          "$skip": 0
        },
        {
          "$limit": 20
        },
        {
          "$addFields": {
            "registration_open": {
              "$and": [
                {
                  "$eq": [
                    "$registration.required",
                    true
                  ]
                },
                {
                  "$or": [
                    {
                      "$eq": [
                        {
                          "$ifNull": [
                            "$registration.deadline",
                            null
                          ]
                        },
                        null
                      ]
                    },
                    {
                      "$gt": [
                        "$registration.deadline",
                        {
                          "$date": "2026-10-09T08:25:04.955Z"
                        }
                      ]
                    }
                  ]
                },
                {
                  "$gt": [
                    "$schedule.start",
                    {
                      "$date": "2026-10-09T08:25:04.955Z"
                    }
                  ]
                }
              ]
            }
          }
        },
        {
          "$project": {
            "description": 0,
            "details": 0,
            "contact": 0,
            "change_log": 0
          }
        },
        {
          "$project": {
            "popularity": 0,
            "_text_score": 0
          }
        }
      ],
      "total": [
        {
          "$count": "n"
        }
      ],
      "by_category": [
        {
          "$group": {
            "_id": "$category",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "count": -1,
            "_id": 1
          }
        }
      ],
      "by_club": [
        {
          "$group": {
            "_id": "$club_id",
            "name": {
              "$first": "$club_snapshot.name"
            },
            "slug": {
              "$first": "$club_snapshot.slug"
            },
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "count": -1,
            "name": 1
          }
        }
      ]
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `FETCH > TEXT_MATCH(events_text) > TEXT_OR > IXSCAN(events_text)` |
|---|---|
| Index | **index scan** on `events_text` |
| nReturned | 1 |
| totalKeysExamined | 3 |
| totalDocsExamined | 6 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

`TEXT_MATCH` over the `events_text` index; no collection scan.

### 3. Top 10 Events to Participate In

**Endpoint:** `GET /home/top-events`  
**Collection:** `events`  
**MongoDB features:** `$lookup` with a correlated sub-pipeline (+ `localField/foreignField`), `$setWindowFields` (max-normalisation across the eligible set), `$map/$filter/$sum`, `$exp`, `$cond`, `$addFields`, `$sort/$limit`

**Purpose.** One pipeline computes the score from windowed engagement (last 7 days) + proximity + urgency, using configurable weights from the `settings` collection. Old all-time views cannot dominate because only interactions inside the window are counted. Each result carries its `score_breakdown` for transparency.

_Parameters used here:_ weights {'saves': 0.3, 'views': 0.2, 'clicks': 0.2, 'proximity': 0.2, 'urgency': 0.1}, window_days 7

<details><summary>Pipeline (12 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published",
      "cancelled_at": null,
      "schedule.start": {
        "$gt": {
          "$date": "2026-10-09T08:25:04.955Z"
        }
      },
      "$or": [
        {
          "registration.required": {
            "$ne": true
          }
        },
        {
          "registration.deadline": null
        },
        {
          "registration.deadline": {
            "$gt": {
              "$date": "2026-10-09T08:25:04.955Z"
            }
          }
        }
      ]
    }
  },
  {
    "$lookup": {
      "from": "event_interactions",
      "localField": "_id",
      "foreignField": "event_id",
      "pipeline": [
        {
          "$match": {
            "ts": {
              "$gte": {
                "$date": "2026-10-02T08:25:04.955Z"
              }
            }
          }
        },
        {
          "$group": {
            "_id": "$type",
            "n": {
              "$sum": 1
            }
          }
        }
      ],
      "as": "ix"
    }
  },
  {
    "$addFields": {
      "w_saves": {
        "$sum": {
          "$map": {
            "input": {
              "$filter": {
                "input": "$ix",
                "cond": {
                  "$eq": [
                    "$$this._id",
                    "save"
                  ]
                }
              }
            },
            "in": "$$this.n"
          }
        }
      },
      "w_views": {
        "$sum": {
          "$map": {
            "input": {
              "$filter": {
                "input": "$ix",
                "cond": {
                  "$eq": [
                    "$$this._id",
                    "view"
                  ]
                }
              }
            },
            "in": "$$this.n"
          }
        }
      },
      "w_clicks": {
        "$sum": {
          "$map": {
            "input": {
              "$filter": {
                "input": "$ix",
                "cond": {
                  "$eq": [
                    "$$this._id",
                    "registration_click"
                  ]
                }
              }
            },
            "in": "$$this.n"
          }
        }
      }
    }
  },
  {
    "$setWindowFields": {
      "output": {
        "max_saves": {
          "$max": "$w_saves",
          "window": {
            "documents": [
              "unbounded",
              "unbounded"
            ]
          }
        },
        "max_views": {
          "$max": "$w_views",
          "window": {
            "documents": [
              "unbounded",
              "unbounded"
            ]
          }
        },
        "max_clicks": {
          "$max": "$w_clicks",
          "window": {
            "documents": [
              "unbounded",
              "unbounded"
            ]
          }
        }
      }
    }
  },
  {
    "$addFields": {
      "components": {
        "saves": {
          "$cond": [
            {
              "$gt": [
                "$max_saves",
                0
              ]
            },
            {
              "$divide": [
                "$w_saves",
                "$max_saves"
              ]
            },
            0
          ]
        },
        "views": {
          "$cond": [
            {
              "$gt": [
                "$max_views",
                0
              ]
            },
            {
              "$divide": [
                "$w_views",
                "$max_views"
              ]
            },
            0
          ]
        },
        "clicks": {
          "$cond": [
            {
              "$gt": [
                "$max_clicks",
                0
              ]
            },
            {
              "$divide": [
                "$w_clicks",
                "$max_clicks"
              ]
            },
            0
          ]
        },
        "proximity": {
          "$exp": {
            "$divide": [
              {
                "$multiply": [
                  -1,
                  {
                    "$divide": [
                      {
                        "$subtract": [
                          "$schedule.start",
                          {
                            "$date": "2026-10-09T08:25:04.955Z"
                          }
                        ]
                      },
                      86400000
                    ]
                  }
                ]
              },
              7
            ]
          }
        },
        "urgency": {
          "$cond": [
            {
              "$and": [
                {
                  "$eq": [
                    "$registration.required",
                    true
                  ]
                },
                {
                  "$ne": [
                    {
                      "$ifNull": [
                        "$registration.deadline",
                        null
                      ]
                    },
                    null
                  ]
                },
                {
                  "$lte": [
                    "$registration.deadline",
                    {
                      "$date": "2026-10-12T08:25:04.955Z"
                    }
                  ]
                }
              ]
            },
            1.0,
            {
              "$cond": [
                {
                  "$eq": [
                    "$registration.required",
                    true
                  ]
                },
                0.5,
                0
              ]
            }
          ]
        }
      }
    }
  },
  {
    "$addFields": {
      "contributions": {
        "saves": {
          "$multiply": [
            0.3,
            "$components.saves"
          ]
        },
        "views": {
          "$multiply": [
            0.2,
            "$components.views"
          ]
        },
        "clicks": {
          "$multiply": [
            0.2,
            "$components.clicks"
          ]
        },
        "proximity": {
          "$multiply": [
            0.2,
            "$components.proximity"
          ]
        },
        "urgency": {
          "$multiply": [
            0.1,
            "$components.urgency"
          ]
        }
      }
    }
  },
  {
    "$addFields": {
      "score": {
        "$add": [
          "$contributions.saves",
          "$contributions.views",
          "$contributions.clicks",
          "$contributions.proximity",
          "$contributions.urgency"
        ]
      }
    }
  },
  {
    "$sort": {
      "score": -1,
      "schedule.start": 1,
      "_id": 1
    }
  },
  {
    "$limit": 10
  },
  {
    "$addFields": {
      "registration_open": {
        "$and": [
          {
            "$eq": [
              "$registration.required",
              true
            ]
          },
          {
            "$or": [
              {
                "$eq": [
                  {
                    "$ifNull": [
                      "$registration.deadline",
                      null
                    ]
                  },
                  null
                ]
              },
              {
                "$gt": [
                  "$registration.deadline",
                  {
                    "$date": "2026-10-09T08:25:04.955Z"
                  }
                ]
              }
            ]
          },
          {
            "$gt": [
              "$schedule.start",
              {
                "$date": "2026-10-09T08:25:04.955Z"
              }
            ]
          }
        ]
      }
    }
  },
  {
    "$project": {
      "description": 0,
      "details": 0,
      "contact": 0,
      "change_log": 0
    }
  },
  {
    "$project": {
      "ix": 0,
      "w_saves": 0,
      "w_views": 0,
      "w_clicks": 0,
      "max_saves": 0,
      "max_views": 0,
      "max_clicks": 0
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `FETCH > IXSCAN(status_start)` |
|---|---|
| Index | **index scan** on `status_start` |
| nReturned | 33 |
| totalKeysExamined | 37 |
| totalDocsExamined | 37 |
| executionTimeMillis | 5 |
| rejected plans | 0 |

Index-served prefix: eligible events by `status` + `schedule.start`. The `$lookup` into `event_interactions` is explained in the next entry.

### 4. Top 10 `$lookup` inner query (per event)

**Endpoint:** `GET /home/top-events` (inside the `$lookup`)  
**Collection:** `event_interactions`  
**MongoDB features:** compound index `{event_id, type, ts}`, range on `ts`

**Purpose.** For each eligible event the `$lookup` runs this query. It must not scan the interaction log; the equality on `event_id` uses the compound index prefix.

```js
db.event_interactions.find({
  "event_id": {
    "$oid": "6ac8a4d2ae2f822d6c0686d2"
  },
  "ts": {
    "$gte": {
      "$date": "2026-10-02T08:25:04.955Z"
    }
  }
})
```

**`explain("executionStats")`:**

| Winning plan | `FETCH > IXSCAN(event_type_ts)` |
|---|---|
| Index | **index scan** on `event_type_ts` |
| nReturned | 29 |
| totalKeysExamined | 33 |
| totalDocsExamined | 29 |
| executionTimeMillis | 0 |
| rejected plans | 1 |

The windowed counts per event come from the index entries for that `event_id` only.

### 5. Suggested for you (logged in)

**Endpoint:** `GET /home/suggested`  
**Collection:** `events`  
**MongoDB features:** `$setIntersection` + `$size` (interest match), `$in` (category/club match), `$exp`, `$cond`, `$nin` (hide already-saved)

**Purpose.** Rule-based personal score `0.35·interest + 0.20·category + 0.20·club + 0.15·date + 0.10·deadline`. Tags and interests are lower-cased on write so comparison is exact and index-friendly.

_Parameters used here:_ Saanvi Nair: interests ['dance', 'public speaking', 'music', 'football', 'machine learning'], 2 followed clubs, 6 saved events excluded

<details><summary>Pipeline (8 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published",
      "cancelled_at": null,
      "schedule.start": {
        "$gt": {
          "$date": "2026-10-09T08:25:04.955Z"
        }
      },
      "$or": [
        {
          "registration.required": {
            "$ne": true
          }
        },
        {
          "registration.deadline": null
        },
        {
          "registration.deadline": {
            "$gt": {
              "$date": "2026-10-09T08:25:04.955Z"
            }
          }
        }
      ],
      "_id": {
        "$nin": [
          {
            "$oid": "6ac8a4d3ae2f822d6c0686ed"
          },
          {
            "$oid": "6ac8a4d3ae2f822d6c068709"
          },
          {
            "$oid": "6ac8a4d3ae2f822d6c068710"
          },
          {
            "$oid": "6ac8a4d3ae2f822d6c068714"
          },
          {
            "$oid": "6ac8a4d3ae2f822d6c068728"
          },
          {
            "$oid": "6ac8a4d4ae2f822d6c068758"
          }
        ]
      }
    }
  },
  {
    "$addFields": {
      "components": {
        "interest": {
          "$divide": [
            {
              "$size": {
                "$setIntersection": [
                  {
                    "$ifNull": [
                      "$tags",
                      []
                    ]
                  },
                  [
                    "dance",
                    "public speaking",
                    "music",
                    "football",
                    "machine learning"
                  ]
                ]
              }
            },
            5
          ]
        },
        "category": {
          "$cond": [
            {
              "$in": [
                "$category",
                [
                  "technical"
                ]
              ]
            },
            1,
            0
          ]
        },
        "club": {
          "$cond": [
            {
              "$in": [
                "$club_id",
                [
                  {
                    "$oid": "6ac8a4d2ae2f822d6c0686bd"
                  },
                  {
                    "$oid": "6ac8a4d2ae2f822d6c0686cd"
                  }
                ]
              ]
            },
            1,
            0
          ]
        },
        "date": {
          "$exp": {
            "$divide": [
              {
                "$multiply": [
                  -1,
                  {
                    "$divide": [
                      {
                        "$subtract": [
                          "$schedule.start",
                          {
                            "$date": "2026-10-09T08:25:04.955Z"
                          }
                        ]
                      },
                      86400000
                    ]
                  }
                ]
              },
              10
            ]
          }
        },
        "deadline": {
          "$cond": [
            {
              "$and": [
                {
                  "$eq": [
                    "$registration.required",
                    true
                  ]
                },
                {
                  "$ne": [
                    {
                      "$ifNull": [
                        "$registration.deadline",
                        null
                      ]
                    },
                    null
                  ]
                },
                {
                  "$gt": [
                    "$registration.deadline",
                    {
                      "$date": "2026-10-09T08:25:04.955Z"
                    }
                  ]
                },
                {
                  "$lte": [
                    "$registration.deadline",
                    {
                      "$date": "2026-10-14T08:25:04.955Z"
                    }
                  ]
                }
              ]
            },
            1,
            0
          ]
        }
      }
    }
  },
  {
    "$addFields": {
      "contributions": {
        "interest": {
          "$multiply": [
            0.35,
            "$components.interest"
          ]
        },
        "category": {
          "$multiply": [
            0.2,
            "$components.category"
          ]
        },
        "club": {
          "$multiply": [
            0.2,
            "$components.club"
          ]
        },
        "date": {
          "$multiply": [
            0.15,
            "$components.date"
          ]
        },
        "deadline": {
          "$multiply": [
            0.1,
            "$components.deadline"
          ]
        }
      }
    }
  },
  {
    "$addFields": {
      "score": {
        "$add": [
          "$contributions.interest",
          "$contributions.category",
          "$contributions.club",
          "$contributions.date",
          "$contributions.deadline"
        ]
      }
    }
  },
  {
    "$sort": {
      "score": -1,
      "schedule.start": 1,
      "_id": 1
    }
  },
  {
    "$limit": 10
  },
  {
    "$addFields": {
      "registration_open": {
        "$and": [
          {
            "$eq": [
              "$registration.required",
              true
            ]
          },
          {
            "$or": [
              {
                "$eq": [
                  {
                    "$ifNull": [
                      "$registration.deadline",
                      null
                    ]
                  },
                  null
                ]
              },
              {
                "$gt": [
                  "$registration.deadline",
                  {
                    "$date": "2026-10-09T08:25:04.955Z"
                  }
                ]
              }
            ]
          },
          {
            "$gt": [
              "$schedule.start",
              {
                "$date": "2026-10-09T08:25:04.955Z"
              }
            ]
          }
        ]
      }
    }
  },
  {
    "$project": {
      "description": 0,
      "details": 0,
      "contact": 0,
      "change_log": 0
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `FETCH > IXSCAN(status_start)` |
|---|---|
| Index | **index scan** on `status_start` |
| nReturned | 27 |
| totalKeysExamined | 37 |
| totalDocsExamined | 37 |
| executionTimeMillis | 0 |
| rejected plans | 1 |

### 6. Popular upcoming (anonymous / no-signal fallback)

**Endpoint:** `GET /home/suggested` (anonymous)  
**Collection:** `events`  
**MongoDB features:** computed pattern (`stats.*` counters), `$addFields`, `$sort`

**Purpose.** Ordering by popularity reads the embedded counters instead of counting interactions, which is why `stats` is embedded (computed pattern).

<details><summary>Pipeline (7 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published",
      "cancelled_at": null,
      "schedule.start": {
        "$gt": {
          "$date": "2026-10-09T08:25:04.955Z"
        }
      },
      "$or": [
        {
          "registration.required": {
            "$ne": true
          }
        },
        {
          "registration.deadline": null
        },
        {
          "registration.deadline": {
            "$gt": {
              "$date": "2026-10-09T08:25:04.955Z"
            }
          }
        }
      ]
    }
  },
  {
    "$addFields": {
      "popularity": {
        "$add": [
          {
            "$multiply": [
              {
                "$ifNull": [
                  "$stats.saves",
                  0
                ]
              },
              3
            ]
          },
          {
            "$multiply": [
              {
                "$ifNull": [
                  "$stats.registration_clicks",
                  0
                ]
              },
              2
            ]
          },
          {
            "$ifNull": [
              "$stats.views",
              0
            ]
          }
        ]
      }
    }
  },
  {
    "$sort": {
      "popularity": -1,
      "schedule.start": 1,
      "_id": 1
    }
  },
  {
    "$limit": 10
  },
  {
    "$addFields": {
      "registration_open": {
        "$and": [
          {
            "$eq": [
              "$registration.required",
              true
            ]
          },
          {
            "$or": [
              {
                "$eq": [
                  {
                    "$ifNull": [
                      "$registration.deadline",
                      null
                    ]
                  },
                  null
                ]
              },
              {
                "$gt": [
                  "$registration.deadline",
                  {
                    "$date": "2026-10-09T08:25:04.955Z"
                  }
                ]
              }
            ]
          },
          {
            "$gt": [
              "$schedule.start",
              {
                "$date": "2026-10-09T08:25:04.955Z"
              }
            ]
          }
        ]
      }
    }
  },
  {
    "$project": {
      "description": 0,
      "details": 0,
      "contact": 0,
      "change_log": 0
    }
  },
  {
    "$project": {
      "popularity": 0
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `FETCH > IXSCAN(status_start)` |
|---|---|
| Index | **index scan** on `status_start` |
| nReturned | 33 |
| totalKeysExamined | 37 |
| totalDocsExamined | 37 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

### 7. Tomorrow / next 7 days

**Endpoint:** `GET /home/tomorrow`, `GET /home/next-7-days`  
**Collection:** `events`  
**MongoDB features:** range `$match` on IST-aligned UTC bounds, `$addFields` for `registration_open`

**Purpose.** Chronological list for an IST day range. Bounds are computed in `core/timeutil.py` (`[00:00 IST, 00:00 IST next day)` converted to UTC).

_Parameters used here:_ next-7-days range

<details><summary>Pipeline (5 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published",
      "cancelled_at": null,
      "schedule.start": {
        "$gte": {
          "$date": "2026-10-09T08:25:04.955Z"
        },
        "$lt": {
          "$date": "2026-10-15T18:30:00Z"
        }
      }
    }
  },
  {
    "$sort": {
      "schedule.start": 1,
      "_id": 1
    }
  },
  {
    "$limit": 50
  },
  {
    "$addFields": {
      "registration_open": {
        "$and": [
          {
            "$eq": [
              "$registration.required",
              true
            ]
          },
          {
            "$or": [
              {
                "$eq": [
                  {
                    "$ifNull": [
                      "$registration.deadline",
                      null
                    ]
                  },
                  null
                ]
              },
              {
                "$gt": [
                  "$registration.deadline",
                  {
                    "$date": "2026-10-09T08:25:04.955Z"
                  }
                ]
              }
            ]
          },
          {
            "$gt": [
              "$schedule.start",
              {
                "$date": "2026-10-09T08:25:04.955Z"
              }
            ]
          }
        ]
      }
    }
  },
  {
    "$project": {
      "description": 0,
      "details": 0,
      "contact": 0,
      "change_log": 0
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `SORT > FETCH > IXSCAN(status_start)` |
|---|---|
| Index | **index scan** on `status_start` |
| nReturned | 20 |
| totalKeysExamined | 20 |
| totalDocsExamined | 20 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

### 8. Featured event

**Endpoint:** `GET /home/featured`  
**Collection:** `events`  
**MongoDB features:** **partial index** `featured_partial` (only documents with `featured.is_featured: true`)

**Purpose.** The most recently featured upcoming event. The partial index contains only the handful of featured events, so it stays tiny regardless of catalogue size.

<details><summary>Pipeline (5 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published",
      "cancelled_at": null,
      "featured.is_featured": true,
      "schedule.start": {
        "$gt": {
          "$date": "2026-10-09T08:25:04.955Z"
        }
      }
    }
  },
  {
    "$sort": {
      "featured.featured_at": -1
    }
  },
  {
    "$limit": 1
  },
  {
    "$addFields": {
      "registration_open": {
        "$and": [
          {
            "$eq": [
              "$registration.required",
              true
            ]
          },
          {
            "$or": [
              {
                "$eq": [
                  {
                    "$ifNull": [
                      "$registration.deadline",
                      null
                    ]
                  },
                  null
                ]
              },
              {
                "$gt": [
                  "$registration.deadline",
                  {
                    "$date": "2026-10-09T08:25:04.955Z"
                  }
                ]
              }
            ]
          },
          {
            "$gt": [
              "$schedule.start",
              {
                "$date": "2026-10-09T08:25:04.955Z"
              }
            ]
          }
        ]
      }
    }
  },
  {
    "$project": {
      "description": 0,
      "details": 0,
      "contact": 0,
      "change_log": 0
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `LIMIT > FETCH > IXSCAN(featured_partial)` |
|---|---|
| Index | **index scan** on `featured_partial` |
| nReturned | 1 |
| totalKeysExamined | 1 |
| totalDocsExamined | 1 |
| executionTimeMillis | 0 |
| rejected plans | 1 |

The planner picks the **partial index** on its own: it holds only the featured events, so it examines 1 key no matter how many events exist.

### 9. Featured events via the partial index

**Endpoint:** `GET /home/featured`  
**Collection:** `events`  
**MongoDB features:** partial index `{featured.featured_at: -1}` where `featured.is_featured == true`

**Purpose.** Same lookup expressed so the partial index is eligible: the filter implies the index's partial expression.

```js
db.events.find({
  "featured.is_featured": true
}).sort({"featured.featured_at": -1}).limit(1)
```

**`explain("executionStats")`:**

| Winning plan | `LIMIT > FETCH > IXSCAN(featured_partial)` |
|---|---|
| Index | **index scan** on `featured_partial` |
| nReturned | 1 |
| totalKeysExamined | 1 |
| totalDocsExamined | 1 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

### 10. Multikey index: events by tag

**Endpoint:** (tag lookups)  
**Collection:** `events`  
**MongoDB features:** multikey index on the `tags` array

**Purpose.** One index entry per array element lets `{tags: 'ai'}` match without scanning documents.

```js
db.events.find({
  "tags": "ai"
})
```

**`explain("executionStats")`:**

| Winning plan | `FETCH > IXSCAN(tags_multikey)` |
|---|---|
| Index | **index scan** on `tags_multikey` |
| nReturned | 4 |
| totalKeysExamined | 4 |
| totalDocsExamined | 4 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

### 11. Multikey index: is this user a club admin?

**Endpoint:** authorization checks, `GET /events/mine`  
**Collection:** `clubs`  
**MongoDB features:** multikey index on `admin_ids`

**Purpose.** `admin_ids` is the single source of truth for membership; authorization asks 'which clubs list me?'.

```js
db.clubs.find({
  "admin_ids": {
    "$oid": "6ac8a4d1ae2f822d6c068697"
  }
})
```

**`explain("executionStats")`:**

| Winning plan | `FETCH > IXSCAN(admin_ids_multikey)` |
|---|---|
| Index | **index scan** on `admin_ids_multikey` |
| nReturned | 0 |
| totalKeysExamined | 0 |
| totalDocsExamined | 0 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

### 12. My saved events

**Endpoint:** `GET /saved-events?upcoming=true`  
**Collection:** `saved_events`  
**MongoDB features:** compound index `{user_id, event_start}` (range + sort without a join), then `$lookup` into `events` by `_id`

**Purpose.** `event_start` is a deliberate denormalised copy, so 'my upcoming saved events' is an index range scan; only the page's events are joined afterwards.

_Parameters used here:_ user Saanvi Nair

<details><summary>Pipeline (6 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "user_id": {
        "$oid": "6ac8a4d1ae2f822d6c068697"
      },
      "event_start": {
        "$gte": {
          "$date": "2026-10-09T08:25:04.955Z"
        }
      }
    }
  },
  {
    "$sort": {
      "event_start": 1,
      "_id": 1
    }
  },
  {
    "$skip": 0
  },
  {
    "$limit": 20
  },
  {
    "$lookup": {
      "from": "events",
      "localField": "event_id",
      "foreignField": "_id",
      "pipeline": [
        {
          "$addFields": {
            "registration_open": {
              "$and": [
                {
                  "$eq": [
                    "$registration.required",
                    true
                  ]
                },
                {
                  "$or": [
                    {
                      "$eq": [
                        {
                          "$ifNull": [
                            "$registration.deadline",
                            null
                          ]
                        },
                        null
                      ]
                    },
                    {
                      "$gt": [
                        "$registration.deadline",
                        {
                          "$date": "2026-10-09T08:25:04.955Z"
                        }
                      ]
                    }
                  ]
                },
                {
                  "$gt": [
                    "$schedule.start",
                    {
                      "$date": "2026-10-09T08:25:04.955Z"
                    }
                  ]
                }
              ]
            }
          }
        },
        {
          "$project": {
            "description": 0,
            "details": 0,
            "contact": 0,
            "change_log": 0
          }
        }
      ],
      "as": "event"
    }
  },
  {
    "$unwind": "$event"
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `SORT > FETCH > IXSCAN(user_event_start)` |
|---|---|
| Index | **index scan** on `user_event_start` |
| nReturned | 6 |
| totalKeysExamined | 6 |
| totalDocsExamined | 6 |
| executionTimeMillis | 1 |
| rejected plans | 1 |

### 13. Calendar month grouped by IST day

**Endpoint:** `GET /calendar?year=2026&month=10`  
**Collection:** `saved_events`  
**MongoDB features:** `$dateToString` with `timezone: Asia/Kolkata`, `$group` + `$push`, `$lookup`

**Purpose.** Range-queries the denormalised `event_start` for an IST month, then groups by IST date inside the database so the day boundary is correct (an event at 00:30 IST belongs to the next IST day even though its UTC date is the previous one).

_Parameters used here:_ 2026-10

<details><summary>Pipeline (6 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "user_id": {
        "$oid": "6ac8a4d1ae2f822d6c068697"
      },
      "event_start": {
        "$gte": {
          "$date": "2026-09-30T18:30:00Z"
        },
        "$lt": {
          "$date": "2026-10-31T18:30:00Z"
        }
      }
    }
  },
  {
    "$sort": {
      "event_start": 1,
      "_id": 1
    }
  },
  {
    "$lookup": {
      "from": "events",
      "localField": "event_id",
      "foreignField": "_id",
      "pipeline": [
        {
          "$addFields": {
            "registration_open": {
              "$and": [
                {
                  "$eq": [
                    "$registration.required",
                    true
                  ]
                },
                {
                  "$or": [
                    {
                      "$eq": [
                        {
                          "$ifNull": [
                            "$registration.deadline",
                            null
                          ]
                        },
                        null
                      ]
                    },
                    {
                      "$gt": [
                        "$registration.deadline",
                        {
                          "$date": "2026-10-09T08:25:04.955Z"
                        }
                      ]
                    }
                  ]
                },
                {
                  "$gt": [
                    "$schedule.start",
                    {
                      "$date": "2026-10-09T08:25:04.955Z"
                    }
                  ]
                }
              ]
            }
          }
        },
        {
          "$project": {
            "description": 0,
            "details": 0,
            "contact": 0,
            "change_log": 0
          }
        }
      ],
      "as": "event"
    }
  },
  {
    "$unwind": "$event"
  },
  {
    "$group": {
      "_id": {
        "$dateToString": {
          "date": "$event_start",
          "format": "%Y-%m-%d",
          "timezone": "Asia/Kolkata"
        }
      },
      "rows": {
        "$push": "$$ROOT"
      }
    }
  },
  {
    "$sort": {
      "_id": 1
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `SORT > FETCH > IXSCAN(user_event_start)` |
|---|---|
| Index | **index scan** on `user_event_start` |
| nReturned | 5 |
| totalKeysExamined | 5 |
| totalDocsExamined | 5 |
| executionTimeMillis | 2 |
| rejected plans | 1 |

### 14. Comment thread (top-level + reply preview)

**Endpoint:** `GET /posts/{id}/comments?replies=3`  
**Collection:** `comments`  
**MongoDB features:** two correlated `$lookup` sub-pipelines (reply preview with `$limit`; reply count with `$count`), index `{post_id, created_at}`

**Purpose.** Pages top-level comments and attaches up to N replies plus the true reply total in one query. Threading is capped at two levels, so one `$lookup` level suffices (no recursion).

_Parameters used here:_ post with 10 comments

<details><summary>Pipeline (6 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "post_id": {
        "$oid": "6ac8a4dcae2f822d6c0694af"
      },
      "parent_id": null
    }
  },
  {
    "$sort": {
      "created_at": 1,
      "_id": 1
    }
  },
  {
    "$skip": 0
  },
  {
    "$limit": 20
  },
  {
    "$lookup": {
      "from": "comments",
      "localField": "_id",
      "foreignField": "parent_id",
      "pipeline": [
        {
          "$sort": {
            "created_at": 1,
            "_id": 1
          }
        },
        {
          "$limit": 3
        }
      ],
      "as": "replies"
    }
  },
  {
    "$lookup": {
      "from": "comments",
      "localField": "_id",
      "foreignField": "parent_id",
      "pipeline": [
        {
          "$match": {
            "status": "active"
          }
        },
        {
          "$count": "n"
        }
      ],
      "as": "reply_total"
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `SORT > FETCH > IXSCAN(post_created)` |
|---|---|
| Index | **index scan** on `post_created` |
| nReturned | 6 |
| totalKeysExamined | 10 |
| totalDocsExamined | 10 |
| executionTimeMillis | 1 |
| rejected plans | 1 |

### 15. Community feed

**Endpoint:** `GET /posts?scope=club&ref_id=…`  
**Collection:** `posts`  
**MongoDB features:** compound index `{scope.type, scope.ref_id, created_at: -1}`

**Purpose.** Feed for one scope (global / event / club) newest first.

```js
db.posts.find({
  "status": "active",
  "scope.type": "global"
}).sort({"created_at": -1}).limit(20)
```

**`explain("executionStats")`:**

| Winning plan | `SORT > FETCH > IXSCAN(scope_created)` |
|---|---|
| Index | **index scan** on `scope_created` |
| nReturned | 8 |
| totalKeysExamined | 8 |
| totalDocsExamined | 8 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

### 16. Post search

**Endpoint:** `GET /posts?q=…`  
**Collection:** `posts`  
**MongoDB features:** text index on `title` + `body`

**Purpose.** Full-text search over posts.

```js
db.posts.find({
  "status": "active",
  "$text": {
    "$search": "campus"
  }
})
```

**`explain("executionStats")`:**

| Winning plan | `FETCH > TEXT_MATCH(posts_text) > FETCH > IXSCAN(posts_text)` |
|---|---|
| Index | **index scan** on `posts_text` |
| nReturned | 1 |
| totalKeysExamined | 1 |
| totalDocsExamined | 2 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

### 17. Analytics overview

**Endpoint:** `GET /analytics/overview`  
**Collection:** `events`  
**MongoDB features:** `$facet` with three independent `$group` branches, computed-pattern counters (`$sum: $stats.saves`)

**Purpose.** Events per category (published), per status (all), and top clubs by saves, in one pass over the collection.

<details><summary>Pipeline (1 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$facet": {
      "by_category": [
        {
          "$match": {
            "status": "published"
          }
        },
        {
          "$group": {
            "_id": "$category",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "count": -1,
            "_id": 1
          }
        }
      ],
      "by_status": [
        {
          "$group": {
            "_id": "$status",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "count": -1,
            "_id": 1
          }
        }
      ],
      "top_clubs": [
        {
          "$match": {
            "status": "published"
          }
        },
        {
          "$group": {
            "_id": "$club_id",
            "name": {
              "$first": "$club_snapshot.name"
            },
            "slug": {
              "$first": "$club_snapshot.slug"
            },
            "events": {
              "$sum": 1
            },
            "saves": {
              "$sum": "$stats.saves"
            },
            "views": {
              "$sum": "$stats.views"
            },
            "registration_clicks": {
              "$sum": "$stats.registration_clicks"
            }
          }
        },
        {
          "$sort": {
            "saves": -1,
            "name": 1
          }
        },
        {
          "$limit": 10
        }
      ]
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `PROJECTION_DEFAULT > COLLSCAN` |
|---|---|
| Index | **no index (collection scan)** |
| nReturned | 55 |
| totalKeysExamined | 0 |
| totalDocsExamined | 55 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

`COLLSCAN` is the *intended* plan here: a whole-collection rollup must read every event, so an index cannot help. It stays cheap because the counters it sums (`stats.*`) are embedded, so no `event_interactions` scan or `$lookup` is needed.

### 18. Engagement funnel (views → saves → registration clicks)

**Endpoint:** `GET /analytics/engagement?days=30`  
**Collection:** `event_interactions`  
**MongoDB features:** range `$match` on `ts`, two-step `$group` (count per event/type, then pivot to columns with `$cond`), `$lookup`, `$round`, `$facet` (rows + totals)

**Purpose.** Per-event funnel with conversion rates; zero denominators yield 0. The interaction log is the source of truth here (counters on events are all-time).

<details><summary>Pipeline (6 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "ts": {
        "$gte": {
          "$date": "2026-09-09T08:25:04.955Z"
        }
      }
    }
  },
  {
    "$group": {
      "_id": {
        "e": "$event_id",
        "t": "$type"
      },
      "n": {
        "$sum": 1
      }
    }
  },
  {
    "$group": {
      "_id": "$_id.e",
      "views": {
        "$sum": {
          "$cond": [
            {
              "$eq": [
                "$_id.t",
                "view"
              ]
            },
            "$n",
            0
          ]
        }
      },
      "saves": {
        "$sum": {
          "$cond": [
            {
              "$eq": [
                "$_id.t",
                "save"
              ]
            },
            "$n",
            0
          ]
        }
      },
      "clicks": {
        "$sum": {
          "$cond": [
            {
              "$eq": [
                "$_id.t",
                "registration_click"
              ]
            },
            "$n",
            0
          ]
        }
      }
    }
  },
  {
    "$lookup": {
      "from": "events",
      "localField": "_id",
      "foreignField": "_id",
      "pipeline": [
        {
          "$project": {
            "title": 1,
            "club_id": 1,
            "club_snapshot.name": 1
          }
        }
      ],
      "as": "event"
    }
  },
  {
    "$unwind": "$event"
  },
  {
    "$facet": {
      "items": [
        {
          "$addFields": {
            "view_to_save": {
              "$cond": [
                {
                  "$gt": [
                    "$views",
                    0
                  ]
                },
                {
                  "$round": [
                    {
                      "$divide": [
                        "$saves",
                        "$views"
                      ]
                    },
                    4
                  ]
                },
                0
              ]
            },
            "save_to_click": {
              "$cond": [
                {
                  "$gt": [
                    "$saves",
                    0
                  ]
                },
                {
                  "$round": [
                    {
                      "$divide": [
                        "$clicks",
                        "$saves"
                      ]
                    },
                    4
                  ]
                },
                0
              ]
            },
            "view_to_click": {
              "$cond": [
                {
                  "$gt": [
                    "$views",
                    0
                  ]
                },
                {
                  "$round": [
                    {
                      "$divide": [
                        "$clicks",
                        "$views"
                      ]
                    },
                    4
                  ]
                },
                0
              ]
            }
          }
        },
        {
          "$sort": {
            "views": -1,
            "saves": -1,
            "_id": 1
          }
        },
        {
          "$limit": 20
        }
      ],
      "totals": [
        {
          "$group": {
            "_id": null,
            "views": {
              "$sum": "$views"
            },
            "saves": {
              "$sum": "$saves"
            },
            "clicks": {
              "$sum": "$clicks"
            }
          }
        }
      ]
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `GROUP > GROUP > FETCH > IXSCAN(ts_ttl)` |
|---|---|
| Index | **index scan** on `ts_ttl` |
| nReturned | 45 |
| totalKeysExamined | 3000 |
| totalDocsExamined | 3000 |
| executionTimeMillis | 11 |
| rejected plans | 0 |

The `ts_ttl` index doubles as the range index for the time window. The 30-day window covers the whole 14-day seed, so every interaction is read here; on a long-lived system the window bounds the work.

### 19. Busiest days and hours (IST)

**Endpoint:** `GET /analytics/busiest-days`  
**Collection:** `events`  
**MongoDB features:** `$isoDayOfWeek` / `$hour` with `timezone`, `$facet` (by weekday, by hour, heatmap)

**Purpose.** Counts published events by the IST weekday/hour of their start, computed server-side in the campus timezone.

<details><summary>Pipeline (3 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "status": "published"
    }
  },
  {
    "$addFields": {
      "dow": {
        "$isoDayOfWeek": {
          "date": "$schedule.start",
          "timezone": "Asia/Kolkata"
        }
      },
      "hr": {
        "$hour": {
          "date": "$schedule.start",
          "timezone": "Asia/Kolkata"
        }
      }
    }
  },
  {
    "$facet": {
      "by_weekday": [
        {
          "$group": {
            "_id": "$dow",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "by_hour": [
        {
          "$group": {
            "_id": "$hr",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "heatmap": [
        {
          "$group": {
            "_id": {
              "d": "$dow",
              "h": "$hr"
            },
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id.d": 1,
            "_id.h": 1
          }
        }
      ]
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `PROJECTION_DEFAULT > IXSCAN(status_start)` |
|---|---|
| Index | **index scan** on `status_start` |
| nReturned | 45 |
| totalKeysExamined | 45 |
| totalDocsExamined | 0 |
| executionTimeMillis | 1 |
| rejected plans | 0 |

This is a **covered query**: `status` and `schedule.start` are both in the `status_start` index, so MongoDB answers from the index alone (`totalDocsExamined` is 0).

### 20. Club analytics

**Endpoint:** `GET /analytics/clubs/{club_id}`  
**Collection:** `events`  
**MongoDB features:** index `{club_id, schedule.start}`, `$facet` (status breakdown, upcoming/past split via `$cond`, engagement totals, top 5)

**Purpose.** Everything a club admin needs about their club from a single pass over that club's events.

_Parameters used here:_ ACM

<details><summary>Pipeline (2 stages, exact JSON the API runs)</summary>

```json
[
  {
    "$match": {
      "club_id": {
        "$oid": "6ac8a4d1ae2f822d6c0686b6"
      }
    }
  },
  {
    "$facet": {
      "by_status": [
        {
          "$group": {
            "_id": "$status",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "count": -1,
            "_id": 1
          }
        }
      ],
      "timing": [
        {
          "$match": {
            "status": "published"
          }
        },
        {
          "$group": {
            "_id": {
              "$cond": [
                {
                  "$gt": [
                    "$schedule.start",
                    {
                      "$date": "2026-10-09T08:25:04.955Z"
                    }
                  ]
                },
                "upcoming",
                "past"
              ]
            },
            "count": {
              "$sum": 1
            }
          }
        }
      ],
      "engagement": [
        {
          "$group": {
            "_id": null,
            "views": {
              "$sum": "$stats.views"
            },
            "saves": {
              "$sum": "$stats.saves"
            },
            "clicks": {
              "$sum": "$stats.registration_clicks"
            }
          }
        }
      ],
      "top": [
        {
          "$sort": {
            "stats.saves": -1,
            "stats.views": -1,
            "_id": 1
          }
        },
        {
          "$limit": 5
        },
        {
          "$project": {
            "title": 1,
            "status": 1,
            "stats": 1
          }
        }
      ]
    }
  }
]
```

</details>

**`explain("executionStats")`** (the `$cursor` stage = the part served by the query planner/indexes):

| Winning plan | `PROJECTION_DEFAULT > FETCH > IXSCAN(club_start)` |
|---|---|
| Index | **index scan** on `club_start` |
| nReturned | 8 |
| totalKeysExamined | 8 |
| totalDocsExamined | 8 |
| executionTimeMillis | 0 |
| rejected plans | 0 |

## Other MongoDB features, demonstrated

### TTL index: interactions expire by themselves

`event_interactions` has `{ts: 1}` with `expireAfterSeconds: 7776000` (90 days). MongoDB's background TTL monitor deletes older documents roughly every 60 seconds; no cron job exists in this project. The oldest seeded interaction is 2026-09-25 (seeded interactions span 14 days, so none expire yet).

```js
db.event_interactions.getIndexes().filter(i => i.name === 'ts_ttl')
```

This is also why the Top 10 uses a *windowed* interaction count while `events.stats.*` holds all-time counters.

### `$jsonSchema` validation (schema where we want it, freedom where we need it)

`events`, `users` and `clubs` carry validators with `validationLevel: moderate`, `validationAction: error`. Only common fields are constrained; `details` is intentionally absent from the schema because its shape depends on `event_type` (Pydantic checks it).

Attempting `db.events.insertOne({title: 'bad', status: 'bogus'})` is rejected by the server itself, bypassing the API:

```
WriteError code 121: Document failed validation
```

<details><summary>Validator on <code>events</code></summary>

```json
{
  "bsonType": "object",
  "required": [
    "title",
    "club_id",
    "creator_id",
    "category",
    "event_type",
    "schedule",
    "status",
    "created_at"
  ],
  "properties": {
    "title": {
      "bsonType": "string",
      "minLength": 1
    },
    "one_liner": {
      "bsonType": "string",
      "maxLength": 160
    },
    "club_id": {
      "bsonType": "objectId"
    },
    "creator_id": {
      "bsonType": "objectId"
    },
    "category": {
      "enum": [
        "technical",
        "cultural",
        "debating",
        "sports",
        "academic",
        "career",
        "hackathon",
        "workshop",
        "competition",
        "seminar",
        "social",
        "gaming",
        "other"
      ]
    },
    "event_type": {
      "enum": [
        "workshop",
        "competition",
        "hackathon",
        "sports_match",
        "cultural_show",
        "seminar",
        "social",
        "other"
      ]
    },
    "tags": {
      "bsonType": "array",
      "items": {
        "bsonType": "string"
      }
    },
    "status": {
      "enum": [
        "draft",
        "pending_review",
        "published",
        "rejected",
        "cancelled"
      ]
    },
    "schedule": {
      "bsonType": "object",
      "required": [
        "start",
        "end"
      ],
      "properties": {
        "start": {
          "bsonType": "date"
        },
        "end": {
          "bsonType": "date"
        }
      }
    },
    "fee": {
      "bsonType": "object",
      "properties": {
        "type": {
          "enum": [
            "free",
            "fixed",
            "per_participant",
            "per_team",
            "not_specified"
          ]
        }
      }
    },
    "team": {
      "bsonType": "object",
      "properties": {
        "type": {
          "enum": [
            "individual",
            "range",
            "fixed",
            "not_applicable",
            "not_specified"
          ]
        }
      }
    },
    "stats": {
      "bsonType": "object",
      "properties": {
        "views": {
          "bsonType": [
            "int",
            "long"
          ]
        },
        "saves": {
          "bsonType": [
            "int",
            "long"
          ]
        },
        "registration_clicks": {
          "bsonType": [
            "int",
            "long"
          ]
        }
      }
    },
    "created_at": {
      "bsonType": "date"
    }
  }
}
```

</details>

### Flexible schema: one collection, eight `details` shapes

| event_type | keys of `details` in the stored document |
|---|---|
| `competition` | `eligibility`, `judging_criteria`, `prizes`, `rounds` |
| `cultural_show` | `artists`, `audition_date`, `auditions_required`, `performances` |
| `hackathon` | `duration_hours`, `max_teams`, `prizes`, `themes`, `tracks` |
| `other` | `extra` |
| `seminar` | `q_and_a_enabled`, `speaker`, `topic` |
| `social` | `extra` |
| `sports_match` | `format`, `match_type`, `sport`, `teams` |
| `workshop` | `bring_own_laptop`, `duration_minutes`, `prerequisites`, `speaker`, `topics` |

All eight live in `events` with no NULL columns and no per-type tables.

### GridFS: posters stored inside MongoDB

41 posters → `fs.files` (metadata) + 41 `fs.chunks` (binary, 261120 bytes each). `events.poster_file_id` references the file; `GET /files/{id}` streams it with `ETag` + immutable cache headers. Replacing a poster uploads the new file first and deletes the old one afterwards.

```json
{
  "_id": {
    "$oid": "6ac8a4d2ae2f822d6c0686d3"
  },
  "filename": "poster-6ac8a4d2ae2f822d6c0686d2",
  "length": 9683,
  "chunkSize": 261120,
  "uploadDate": {
    "$date": "2026-10-09T08:24:50.670Z"
  },
  "metadata": {
    "content_type": "image/png",
    "event_id": {
      "$oid": "6ac8a4d2ae2f822d6c0686d2"
    },
    "kind": "poster"
  }
}
```

Indexes: `fs.files` ['_id_', 'filename_1_uploadDate_1'], `fs.chunks` ['_id_', 'files_id_1_n_1'] (`files_id, n` lets chunks stream in order).

### Multi-document transactions

Used where one logical action touches several documents; each is covered by a forced-failure rollback test:

| Action | Writes (all-or-nothing) | Rollback test |
|---|---|---|
| Save an event | `saved_events` insert + `events.stats.saves` `$inc` + `event_interactions` insert | `tests/test_saved.py::test_save_rolls_back_on_midway_failure` |
| Unsave | `saved_events` delete + `$inc -1` + retract the save interaction | `test_unsave_rolls_back_on_midway_failure` |
| Comment | `comments` insert + `posts.comment_count` `$inc` + `$push` to `recent_comments` with `$slice: -3` | `tests/test_community.py::test_comment_rolls_back_on_midway_failure` |
| React (toggle) | `reactions` insert/update/delete + counter `$inc`s | `test_reaction_rolls_back_on_failure` |
| Rename a club | `clubs` update + `events.club_snapshot.name` `update_many` | `tests/test_events.py::test_club_rename_updates_event_snapshots` |
| Edit an event's schedule | `events` update + `saved_events.event_start` `update_many` | `test_schedule_edit_updates_denormalized_saved_events` |

A control test (`test_without_transaction_the_failure_would_leave_partial_state`) shows the same writes without a transaction leave counters and logs disagreeing. Transactions need a replica set, which is why `docker-compose.yml` runs a single-node replica set.
