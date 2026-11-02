# Recorded answers of Amazon S3's ListObjectsV2

Real answers of the Scottish Remote Sensing Portal's open bucket (`https://srsp-open-data.s3.eu-west-2.amazonaws.com`,
anonymous GET over HTTPS), recorded with curl and requests on 2026-11-02 for the offline tests of
`sources/indexes/s3listing.py` (`tests/test_scotland_nrw_trento.py`), which serves them again with
`tests/http_server.py`. They are no index cassette of `tests/test_parts.py` (no `answers.json`): the test adds
each answer to the server under its query.

| File | Request (`GET /?...`) | Answer |
| --- | --- | --- |
| `srsp/page-1.xml` | `list-type=2&prefix=lidar/orkney-islands-council-23/dtm/27700/gridded/HY17&max-keys=2` | 200, two keys, `IsTruncated` true, a `NextContinuationToken` |
| `srsp/page-2.xml` | the same with `continuation-token=<the token of page 1>` | 200, the last key, `IsTruncated` false |
| `srsp/empty.xml` | `list-type=2&prefix=lidar/orkney-islands-council-23/dtm/27700/gridded/HY99&max-keys=2` | 200, `KeyCount` 0 |
| `srsp/error-token.xml` | `list-type=2&prefix=x&continuation-token=bogus` | 400, `<Error>` `InvalidArgument` |
| `srsp/error-bucket.xml` | `list-type=2&prefix=x` of a bucket that does not exist (`srsp-open-data-nonexistent-xyz`) | 404, `<Error>` `NoSuchBucket` |

The listed files are the Orkney Islands Council's LiDAR 2023 (DTM, 0.5 m), published by the Scottish Government
on the Scottish Remote Sensing Portal under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
(the bucket's entry in the Registry of Open Data on AWS, `scottish-lidar`). Only names, sizes, dates and ETags of
three files are recorded, no data.
