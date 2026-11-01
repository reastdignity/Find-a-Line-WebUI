"""The sources' declarations as they are: the order of SOURCES, every layer's folder, version and
credit, the cache paths of sample tiles and the offline country boxes. Any refactoring of sources/
must keep these (the cache would be fetched again or not found otherwise)."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402

IDS = ["geoportal", "swisstopo", "slovakia", "malta", "malta2012", "spain_canarias", "spain", "alaska",
       "alaska_ifsar", "usa", "usgs10m", "austria", "wales", "england", "hesse",
       "mecklenburg_vorpommern", "saxony_anhalt", "lower_saxony", "south_tyrol", "luxembourg", "denmark",
       "finland", "europe", "nasadem"]

# Every source and layer as it was declared on 2026-10-31 (sources.py before the package)
DECLARED = {'geoportal': {'crs': 'EPSG:2180',
                          'countries': ('pl',),
                          'bbox': None,
                          'fallbacks': ['europe'],
                          'grid_origin': (0.5, 0.5),
                          'default_resolution': 1.0,
                          'instead_without_data': None,
                          'local_crs': 'utm_crs',
                          'ortho': 'poland/ortho/live',
                          'credits': ['NMT / NMPT (GUGiK, Poland)'],
                          'nmt': {'class': 'SheetTiles',
                                  'description': 'NMT (digital terrain model)',
                                  'folder': 'poland/nmt',
                                  'prefix': 'SkorowidzNMT',
                                  'native_res': 1.0,
                                  'processing': 1,
                                  'ttl_days': None,
                                  'credit': 'NMT / NMPT (GUGiK, Poland)',
                                  'shift': (0.0, 0.0),
                                  'index_url': 'https://mapy.geoportal.gov.pl/wss/service/PZGIK/NumerycznyModelTerenuEVRF2007/WFS/Skorowidze'},
                          'nmpt': {'class': 'SheetTiles',
                                   'description': 'NMPT (digital surface model: trees, buildings)',
                                   'folder': 'poland/nmpt',
                                   'prefix': 'SkorowidzNMPT',
                                   'native_res': 1.0,
                                   'processing': 1,
                                   'ttl_days': None,
                                   'credit': 'NMT / NMPT (GUGiK, Poland)',
                                   'shift': (0.0, 0.0),
                                   'index_url': 'https://mapy.geoportal.gov.pl/wss/service/PZGIK/NumerycznyModelPokryciaTerenuEVRF2007/WFS/Skorowidze'}},
            'swisstopo': {'crs': 'EPSG:2056',
                          'countries': ('ch', 'li'),
                          'bbox': None,
                          'fallbacks': ['europe'],
                          'grid_origin': (0.0, 0.0),
                          'default_resolution': 1.0,
                          'instead_without_data': None,
                          'local_crs': 'utm_crs',
                          'ortho': 'switzerland/ortho/live',
                          'credits': ['swissALTI3D / swissSURFACE3D (swisstopo)'],
                          'nmt': {'class': 'StacTiles',
                                  'description': 'swissALTI3D (terrain)',
                                  'folder': 'switzerland/swissalti3d',
                                  'prefix': 'ch.swisstopo.swissalti3d',
                                  'native_res': 0.5,
                                  'processing': 1,
                                  'ttl_days': None,
                                  'credit': 'swissALTI3D / swissSURFACE3D (swisstopo)',
                                  'shift': (0.0, 0.0),
                                  'index_url': 'https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.swissalti3d/items'},
                          'nmpt': {'class': 'StacTiles',
                                   'description': 'swissSURFACE3D Raster (trees, buildings)',
                                   'folder': 'switzerland/swisssurface3d',
                                   'prefix': 'ch.swisstopo.swisssurface3d-raster',
                                   'native_res': 0.5,
                                   'processing': 1,
                                   'ttl_days': None,
                                   'credit': 'swissALTI3D / swissSURFACE3D (swisstopo)',
                                   'shift': (0.0, 0.0),
                                   'index_url': 'https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.swisssurface3d-raster/items'}},
            'slovakia': {'crs': 'EPSG:8353',
                         'countries': ('sk',),
                         'bbox': None,
                         'fallbacks': ['europe'],
                         'grid_origin': (0.0, 0.0),
                         'default_resolution': 1.0,
                         'instead_without_data': None,
                         'local_crs': 'utm_crs',
                         'ortho': 'slovakia/ortho/live',
                         'credits': ['DMR 5.0 / DMP 1.0 (ÚGKK SR, Slovakia)'],
                         'nmt': {'class': 'GridTiles',
                                 'description': 'DMR 5.0 (terrain)',
                                 'folder': 'slovakia/dmr5/5.0/epsg8353-1m-2km',
                                 'prefix': None,
                                 'native_res': 1.0,
                                 'processing': 1,
                                 'ttl_days': None,
                                 'credit': 'DMR 5.0 / DMP 1.0 (ÚGKK SR, Slovakia)',
                                 'shift': (0.0, 0.0)},
                         'nmpt': {'class': 'GridTiles',
                                  'description': 'DMP 1.0 (trees, buildings)',
                                  'folder': 'slovakia/dmp1/1.0/epsg8353-1m-2km',
                                  'prefix': None,
                                  'native_res': 1.0,
                                  'processing': 1,
                                  'ttl_days': None,
                                  'credit': 'DMR 5.0 / DMP 1.0 (ÚGKK SR, Slovakia)',
                                  'shift': (0.0, 0.0)}},
            'malta': {'crs': 'EPSG:32633',
                      'countries': ('mt',),
                      'bbox': None,
                      'fallbacks': ['europe'],
                      'grid_origin': (0.0, 0.0),
                      'default_resolution': 1.0,
                      'instead_without_data': None,
                      'local_crs': 'utm_crs',
                      'ortho': 'malta/ortho/2018',
                      'credits': ['Malta LiDAR 2018 (Planning Authority, MSDI)'],
                      'nmt': {'class': 'WcsTiles',
                              'description': 'DTM (terrain) Malta 2018',
                              'folder': 'malta/dtm/2018',
                              'prefix': None,
                              'native_res': 0.15,
                              'processing': 1,
                              'ttl_days': None,
                              'credit': 'Malta LiDAR 2018 (Planning Authority, MSDI)',
                              'shift': (0.0, 0.0),
                              'url': 'https://malta.coverage.wetransform.eu/dtm_1m_2018/ows',
                              'coverage': 'dtm_1m_2018',
                              'crs': 'EPSG:32633',
                              'axes': ('E', 'N'),
                              'fmt': 'image/tiff',
                              'fetch_res': 1.0,
                              'tile_px': 2000},
                      'nmpt': {'class': 'WcsTiles',
                               'description': 'DSM (trees, buildings) Malta 2018',
                               'folder': 'malta/dsm/2018',
                               'prefix': None,
                               'native_res': 0.15,
                               'processing': 1,
                               'ttl_days': None,
                               'credit': 'Malta LiDAR 2018 (Planning Authority, MSDI)',
                               'shift': (0.0, 0.0),
                               'url': 'https://malta.coverage.wetransform.eu/dsm_1m_2018/ows',
                               'coverage': 'dsm_1m_2018',
                               'crs': 'EPSG:32633',
                               'axes': ('E', 'N'),
                               'fmt': 'image/tiff',
                               'fetch_res': 1.0,
                               'tile_px': 2000}},
            'malta2012': {'crs': 'EPSG:25833',
                          'countries': (),
                          'bbox': None,
                          'fallbacks': ['malta'],
                          'grid_origin': (0.0, 0.0),
                          'default_resolution': 1.0,
                          'instead_without_data': None,
                          'local_crs': 'utm_crs',
                          'ortho': 'malta/ortho/2018',
                          'credits': ['Malta LiDAR 2012 (Planning Authority, MSDI)'],
                          'nmt': {'class': 'WcsTiles',
                                  'description': 'DTM (terrain) Malta 2012',
                                  'folder': 'malta/dtm/2012',
                                  'prefix': None,
                                  'native_res': 1.0,
                                  'processing': 1,
                                  'ttl_days': None,
                                  'credit': 'Malta LiDAR 2012 (Planning Authority, MSDI)',
                                  'shift': (-56.0, -196.0),
                                  'url': 'https://malta.coverage.wetransform.eu/dtm_1m_2012/ows',
                                  'coverage': 'dtm_1m_2012',
                                  'crs': 'EPSG:25833',
                                  'axes': ('E', 'N'),
                                  'fmt': 'image/tiff',
                                  'fetch_res': 1.0,
                                  'tile_px': 2000},
                          'nmpt': {'class': 'WcsTiles',
                                   'description': 'DSM (trees, buildings) Malta 2012',
                                   'folder': 'malta/dsm/2012',
                                   'prefix': None,
                                   'native_res': 1.0,
                                   'processing': 1,
                                   'ttl_days': None,
                                   'credit': 'Malta LiDAR 2012 (Planning Authority, MSDI)',
                                   'shift': (-56.0, -196.0),
                                   'url': 'https://malta.coverage.wetransform.eu/dsm_1m_2012/ows',
                                   'coverage': 'dsm_1m_2012',
                                   'crs': 'EPSG:25833',
                                   'axes': ('E', 'N'),
                                   'fmt': 'image/tiff',
                                   'fetch_res': 1.0,
                                   'tile_px': 2000}},
            'spain_canarias': {'crs': 'EPSG:4083',
                               'countries': ('es',),
                               'bbox': (27.0, 29.6, -18.6, -13.0),
                               'fallbacks': ['europe'],
                               'grid_origin': (0.0, 0.0),
                               'default_resolution': 5.0,
                               'instead_without_data': None,
                               'local_crs': 'utm_crs',
                               'ortho': 'spain/ortho/live',
                               'credits': ['MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)'],
                               'nmt': {'class': 'WcsTiles',
                                       'description': 'MDT05 (terrain) Canary Islands',
                                       'folder': 'spain/mdt05/live',
                                       'prefix': None,
                                       'native_res': 5.0,
                                       'processing': 1,
                                       'ttl_days': 730,
                                       'credit': 'MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)',
                                       'shift': (0.0, 0.0),
                                       'url': 'https://servicios.idee.es/wcs-inspire/mdt',
                                       'coverage': 'Elevacion4083_5',
                                       'crs': 'EPSG:4083',
                                       'axes': ('x', 'y'),
                                       'fmt': 'application/asc',
                                       'fetch_res': 5.0,
                                       'tile_px': 2000},
                               'nmpt': {'class': 'WcsTiles',
                                        'description': 'MDS05 (trees, buildings) Canary Islands',
                                        'folder': 'spain/mds05/live',
                                        'prefix': None,
                                        'native_res': 5.0,
                                        'processing': 1,
                                        'ttl_days': 730,
                                        'credit': 'MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)',
                                        'shift': (0.0, 0.0),
                                        'url': 'https://wcs-mds.idee.es/mds',
                                        'coverage': 'mds05',
                                        'crs': 'EPSG:25830',
                                        'axes': ('x', 'y'),
                                        'fmt': 'application/asc',
                                        'fetch_res': 5.0,
                                        'tile_px': 2000}},
            'spain': {'crs': 'EPSG:25830',
                      'countries': ('es',),
                      'bbox': None,
                      'fallbacks': ['europe'],
                      'grid_origin': (0.0, 0.0),
                      'default_resolution': 5.0,
                      'instead_without_data': None,
                      'local_crs': 'utm_crs',
                      'ortho': 'spain/ortho/live',
                      'credits': ['MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)'],
                      'nmt': {'class': 'WcsTiles',
                              'description': 'MDT05 (terrain) Spain',
                              'folder': 'spain/mdt05/live',
                              'prefix': None,
                              'native_res': 5.0,
                              'processing': 1,
                              'ttl_days': 730,
                              'credit': 'MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)',
                              'shift': (0.0, 0.0),
                              'url': 'https://servicios.idee.es/wcs-inspire/mdt',
                              'coverage': 'Elevacion25830_5',
                              'crs': 'EPSG:25830',
                              'axes': ('x', 'y'),
                              'fmt': 'application/asc',
                              'fetch_res': 5.0,
                              'tile_px': 2000},
                      'nmpt': {'class': 'WcsTiles',
                               'description': 'MDS05 (trees, buildings) Spain',
                               'folder': 'spain/mds05/live',
                               'prefix': None,
                               'native_res': 5.0,
                               'processing': 1,
                               'ttl_days': 730,
                               'credit': 'MDT05 / MDS05 (IGN Spain, PNOA-LiDAR)',
                               'shift': (0.0, 0.0),
                               'url': 'https://wcs-mds.idee.es/mds',
                               'coverage': 'mds05',
                               'crs': 'EPSG:25830',
                               'axes': ('x', 'y'),
                               'fmt': 'application/asc',
                               'fetch_res': 5.0,
                               'tile_px': 2000}},
            'alaska': {'crs': None,
                       'countries': ('us',),
                       'bbox': (51.0, 71.5, -180.0, -129.9),
                       'fallbacks': ['alaska_ifsar', 'usgs10m'],
                       'grid_origin': (0.0, 0.0),
                       'default_resolution': 1.0,
                       'instead_without_data': 'alaska_ifsar',
                       'local_crs': 'nad83_utm_crs',
                       'ortho': 'usa/ortho/live',
                       'credits': ['3DEP 1 m DEM (USGS)'],
                       'nmt': {'class': 'Usgs1mBlocks',
                               'description': '3DEP 1 m DEM (terrain)',
                               'folder': 'usa/3dep-1m',
                               'prefix': 'dem1m',
                               'native_res': 1.0,
                               'processing': 1,
                               'ttl_days': None,
                               'credit': '3DEP 1 m DEM (USGS)',
                               'shift': (0.0, 0.0),
                               'index_url': 'https://tnmaccess.nationalmap.gov/api/v1/products'},
                       'nmpt': None},
            'alaska_ifsar': {'crs': None,
                             'countries': (),
                             'bbox': None,
                             'fallbacks': ['usgs10m'],
                             'grid_origin': (0.0, 0.0),
                             'default_resolution': 5.0,
                             'instead_without_data': None,
                             'local_crs': 'nad83_utm_crs',
                             'ortho': 'usa/ortho/live',
                             'credits': ['3DEP Alaska IfSAR 5 m DTM (USGS)'],
                             'nmt': {'class': 'IfsarBlocks',
                                     'description': '3DEP Alaska IfSAR 5 m DTM (terrain)',
                                     'folder': 'usa/ifsar-5m',
                                     'prefix': 'ifsar5m',
                                     'native_res': 5.0,
                                     'processing': 1,
                                     'ttl_days': None,
                                     'credit': '3DEP Alaska IfSAR 5 m DTM (USGS)',
                                     'shift': (0.0, 0.0),
                                     'index_url': 'https://tnmaccess.nationalmap.gov/api/v1/products'},
                             'nmpt': None},
            'usa': {'crs': None,
                    'countries': ('us', 'pr', 'vi'),
                    'bbox': None,
                    'fallbacks': ['usgs10m'],
                    'grid_origin': (0.0, 0.0),
                    'default_resolution': 1.0,
                    'instead_without_data': None,
                    'local_crs': 'nad83_utm_crs',
                    'ortho': 'usa/ortho/live',
                    'credits': ['3DEP 1 m DEM (USGS)'],
                    'nmt': {'class': 'Usgs1mBlocks',
                            'description': '3DEP 1 m DEM (terrain)',
                            'folder': 'usa/3dep-1m',
                            'prefix': 'dem1m',
                            'native_res': 1.0,
                            'processing': 1,
                            'ttl_days': None,
                            'credit': '3DEP 1 m DEM (USGS)',
                            'shift': (0.0, 0.0),
                            'index_url': 'https://tnmaccess.nationalmap.gov/api/v1/products'},
                    'nmpt': None},
            'usgs10m': {'crs': None,
                        'countries': (),
                        'bbox': None,
                        'fallbacks': ['europe'],
                        'grid_origin': (0.0, 0.0),
                        'default_resolution': 10.0,
                        'instead_without_data': None,
                        'local_crs': 'nad83_utm_crs',
                        'ortho': 'usa/ortho/live',
                        'credits': ['3DEP 1/3 arc-second DEM (USGS)'],
                        'nmt': {'class': 'DegreeBlocks',
                                'description': '3DEP 1/3 arc-second DEM (terrain)',
                                'folder': 'usa/3dep-13/live',
                                'prefix': None,
                                'native_res': 10.0,
                                'processing': 1,
                                'ttl_days': 730,
                                'credit': '3DEP 1/3 arc-second DEM (USGS)',
                                'shift': (0.0, 0.0)},
                        'nmpt': None},
            'austria': {'crs': 'EPSG:3035',
                   'countries': ('at',),
                   'bbox': None,
                   'fallbacks': ['europe'],
                   'grid_origin': (0.5, 0.5),
                   'default_resolution': 1.0,
                   'instead_without_data': None,
                   'local_crs': 'utm_crs',
                   'ortho': 'austria/ortho/live',
                   'credits': ['ALS DTM / DSM Höhenraster 1 m (BEV, Austria)'],
                   'nmt': {'class': 'FileBlocks',
                           'description': 'ALS DTM 1 m (terrain)',
                           'folder': 'austria/als-dtm/20250915',
                           'prefix': None,
                           'native_res': 1.0,
                           'processing': 1,
                           'ttl_days': None,
                           'credit': 'ALS DTM / DSM Höhenraster 1 m (BEV, Austria)',
                           'shift': (0.0, 0.0)},
                   'nmpt': {'class': 'FileBlocks',
                            'description': 'ALS DSM 1 m (trees, buildings)',
                            'folder': 'austria/als-dsm/20250915',
                            'prefix': None,
                            'native_res': 1.0,
                            'processing': 1,
                            'ttl_days': None,
                            'credit': 'ALS DTM / DSM Höhenraster 1 m (BEV, Austria)',
                            'shift': (0.0, 0.0)}},
            'wales': {'crs': 'EPSG:27700',
                      'countries': ('gb',),
                      'bbox': None,
                      'fallbacks': ['europe'],
                      'grid_origin': (0.0, 0.0),
                      'default_resolution': 1.0,
                      'instead_without_data': None,
                      'local_crs': 'utm_crs',
                      'ortho': None,
                      'credits': ['Welsh Government LiDAR 2020-22 DTM / DSM 1 m (DataMapWales)'],
                      'nmt': {'class': 'FileBlocks',
                              'description': 'Welsh LiDAR DTM 1 m (terrain)',
                              'folder': 'wales/lidar-dtm/20241004',
                              'prefix': None,
                              'native_res': 1.0,
                              'processing': 1,
                              'ttl_days': None,
                              'credit': 'Welsh Government LiDAR 2020-22 DTM / DSM 1 m (DataMapWales)',
                              'shift': (0.0, 0.0)},
                      'nmpt': {'class': 'FileBlocks',
                               'description': 'Welsh LiDAR DSM 1 m (trees, buildings)',
                               'folder': 'wales/lidar-dsm/20241004',
                               'prefix': None,
                               'native_res': 1.0,
                               'processing': 1,
                               'ttl_days': None,
                               'credit': 'Welsh Government LiDAR 2020-22 DTM / DSM 1 m (DataMapWales)',
                               'shift': (0.0, 0.0)}},
            'england': {'crs': 'EPSG:27700',
                        'countries': ('gb',),
                        'bbox': None,
                        'fallbacks': ['europe'],
                        'grid_origin': (0.0, 0.0),
                        'default_resolution': 1.0,
                        'instead_without_data': None,
                        'local_crs': 'utm_crs',
                        'ortho': None,
                        'credits': ['LIDAR Composite DTM / First Return DSM 2022, 1 m (Environment Agency, England)'],
                        'nmt': {'class': 'WcsTiles',
                                'description': 'EA LIDAR Composite DTM 1 m (terrain)',
                                'folder': 'england/lidar-composite-dtm/2022',
                                'prefix': None,
                                'native_res': 1.0,
                                'processing': 1,
                                'ttl_days': None,
                                'credit': 'LIDAR Composite DTM / First Return DSM 2022, 1 m (Environment Agency, '
                                          'England)',
                                'shift': (0.0, 0.0),
                                'url': 'https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs',
                                'coverage': '13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m',
                                'crs': 'EPSG:27700',
                                'axes': ('E', 'N'),
                                'fmt': 'image/tiff',
                                'fetch_res': 1.0,
                                'tile_px': 2000},
                        'nmpt': {'class': 'WcsTiles',
                                 'description': 'EA LIDAR Composite First Return DSM 1 m (trees, buildings)',
                                 'folder': 'england/lidar-composite-dsm/2022',
                                 'prefix': None,
                                 'native_res': 1.0,
                                 'processing': 1,
                                 'ttl_days': None,
                                 'credit': 'LIDAR Composite DTM / First Return DSM 2022, 1 m (Environment Agency, '
                                           'England)',
                                 'shift': (0.0, 0.0),
                                 'url': 'https://environment.data.gov.uk/spatialdata/lidar-composite-digital-surface-model-first-return-dsm-1m/wcs',
                                 'coverage': 'df4e3ec3-315e-48aa-aaaf-b5ae74d7b2bb__Lidar_Composite_Elevation_FZ_DSM_1m',
                                 'crs': 'EPSG:27700',
                                 'axes': ('E', 'N'),
                                 'fmt': 'image/tiff',
                                 'fetch_res': 1.0,
                                 'tile_px': 2000}},
            'hesse': {'crs': 'EPSG:25832',
                      'countries': ('de',),
                      'bbox': None,
                      'fallbacks': ['europe'],
                      'grid_origin': (0.0, 0.0),
                      'default_resolution': 1.0,
                      'instead_without_data': None,
                      'local_crs': 'utm_crs',
                      'ortho': 'hesse/ortho/live',
                      'credits': ['DGM1 / DOM1 (HVBG, Hesse)'],
                      'nmt': {'class': 'WcsTiles',
                              'description': 'DGM1 (terrain)',
                              'folder': 'hesse/dgm1/live',
                              'prefix': None,
                              'native_res': 1.0,
                              'processing': 1,
                              'ttl_days': 730,
                              'credit': 'DGM1 / DOM1 (HVBG, Hesse)',
                              'shift': (0.0, 0.0),
                              'url': 'https://inspire-hessen.de/raster/dgm1/ows',
                              'coverage': 'he_dgm1',
                              'crs': 'EPSG:25832',
                              'axes': ('E', 'N'),
                              'fmt': 'image/tiff',
                              'fetch_res': 1.0,
                              'tile_px': 2000},
                      'nmpt': {'class': 'WcsTiles',
                               'description': 'DOM1 (trees, buildings)',
                               'folder': 'hesse/dom1/live',
                               'prefix': None,
                               'native_res': 1.0,
                               'processing': 1,
                               'ttl_days': 730,
                               'credit': 'DGM1 / DOM1 (HVBG, Hesse)',
                               'shift': (0.0, 0.0),
                               'url': 'https://inspire-hessen.de/raster/dom1/ows',
                               'coverage': 'dom1',
                               'crs': 'EPSG:25832',
                               'axes': ('E', 'N'),
                               'fmt': 'image/tiff',
                               'fetch_res': 1.0,
                               'tile_px': 2000}},
            'mecklenburg_vorpommern': {'crs': 'EPSG:25833',
                                       'countries': ('de',),
                                       'bbox': None,
                                       'fallbacks': ['europe'],
                                       'grid_origin': (0.0, 0.0),
                                       'default_resolution': 1.0,
                                       'instead_without_data': None,
                                       'local_crs': 'utm_crs',
                                       'ortho': 'mecklenburg_vorpommern/ortho/live',
                                       'credits': ['DGM1 / DOM1 (LAiV, Mecklenburg-Vorpommern)'],
                                       'nmt': {'class': 'WcsTiles',
                                               'description': 'DGM1 (terrain)',
                                               'folder': 'mecklenburg_vorpommern/dgm1/live',
                                               'prefix': None,
                                               'native_res': 1.0,
                                               'processing': 1,
                                               'ttl_days': 730,
                                               'credit': 'DGM1 / DOM1 (LAiV, Mecklenburg-Vorpommern)',
                                               'shift': (0.0, 0.0),
                                               'url': 'https://www.geodaten-mv.de/dienste/inspire_el_dgm_wcs',
                                               'coverage': 'mv_dgm',
                                               'crs': 'EPSG:25833',
                                               'axes': ('x', 'y'),
                                               'fmt': 'image/tiff',
                                               'fetch_res': 1.0,
                                               'tile_px': 2000},
                                       'nmpt': {'class': 'WcsTiles',
                                                'description': 'DOM1 (trees, buildings)',
                                                'folder': 'mecklenburg_vorpommern/dom1/live',
                                                'prefix': None,
                                                'native_res': 1.0,
                                                'processing': 1,
                                                'ttl_days': 730,
                                                'credit': 'DGM1 / DOM1 (LAiV, Mecklenburg-Vorpommern)',
                                                'shift': (0.0, 0.0),
                                                'url': 'https://www.geodaten-mv.de/dienste/dom_wcs',
                                                'coverage': 'mv_dom1',
                                                'crs': 'EPSG:25833',
                                                'axes': ('x', 'y'),
                                                'fmt': 'image/tiff',
                                                'fetch_res': 1.0,
                                                'tile_px': 2000}},
            'saxony_anhalt': {'crs': 'EPSG:25832',
                          'countries': ('de',),
                          'bbox': None,
                          'fallbacks': ['europe'],
                          'grid_origin': (0.0, 0.0),
                          'default_resolution': 1.0,
                          'instead_without_data': None,
                          'local_crs': 'utm_crs',
                          'ortho': 'saxony_anhalt/ortho/live',
                          'credits': ['DGM1 / DOM1 (LVermGeo, Saxony-Anhalt)'],
                          'nmt': {'class': 'WcsTiles',
                                  'description': 'DGM1 (terrain)',
                                  'folder': 'saxony_anhalt/dgm1/live',
                                  'prefix': None,
                                  'native_res': 1.0,
                                  'processing': 1,
                                  'ttl_days': 730,
                                  'credit': 'DGM1 / DOM1 (LVermGeo, Saxony-Anhalt)',
                                  'shift': (0.0, 0.0),
                                  'url': 'https://geodatenportal.sachsen-anhalt.de/ows_WCS_ST_DGM1',
                                  'coverage': 'Coverage1',
                                  'crs': 'EPSG:25832',
                                  'axes': ('x', 'y'),
                                  'fmt': 'image/tiff',
                                  'fetch_res': 1.0,
                                  'tile_px': 2000},
                          'nmpt': {'class': 'WcsTiles',
                                  'description': 'DOM1 (trees, buildings)',
                                  'folder': 'saxony_anhalt/dom1/live',
                                  'prefix': None,
                                  'native_res': 1.0,
                                  'processing': 1,
                                  'ttl_days': 730,
                                  'credit': 'DGM1 / DOM1 (LVermGeo, Saxony-Anhalt)',
                                  'shift': (0.0, 0.0),
                                  'url': 'https://geodatenportal.sachsen-anhalt.de/ows_WCS_ST_DOM1',
                                  'coverage': 'Coverage1',
                                  'crs': 'EPSG:25832',
                                  'axes': ('x', 'y'),
                                  'fmt': 'image/tiff',
                                  'fetch_res': 1.0,
                                  'tile_px': 2000}},
            'lower_saxony': {'crs': 'EPSG:25832',
                         'countries': ('de',),
                         'bbox': None,
                         'fallbacks': ['europe'],
                         'grid_origin': (0.0, 0.0),
                         'default_resolution': 1.0,
                         'instead_without_data': None,
                         'local_crs': 'utm_crs',
                         'ortho': 'lower_saxony/ortho/live',
                         'credits': ['DGM1 / DOM1 (LGLN, Lower Saxony)'],
                         'nmt': {'class': 'StacTiles',
                                 'description': 'DGM1 (terrain)',
                                 'folder': 'lower_saxony/dgm1/live',
                                 'prefix': 'dgm1',
                                 'native_res': 1.0,
                                 'processing': 1,
                                 'ttl_days': 730,
                                 'credit': 'DGM1 / DOM1 (LGLN, Lower Saxony)',
                                 'shift': (0.0, 0.0),
                                 'index_url': 'https://dgm.stac.lgln.niedersachsen.de/collections/dgm1/items'},
                         'nmpt': {'class': 'StacTiles',
                                 'description': 'DOM1 (trees, buildings)',
                                 'folder': 'lower_saxony/dom1/live',
                                 'prefix': 'dom1',
                                 'native_res': 1.0,
                                 'processing': 1,
                                 'ttl_days': 730,
                                 'credit': 'DGM1 / DOM1 (LGLN, Lower Saxony)',
                                 'shift': (0.0, 0.0),
                                 'index_url': 'https://dom.stac.lgln.niedersachsen.de/collections/dom1/items'}},
            'south_tyrol': {'crs': 'EPSG:25832',
                            'countries': ('it',),
                            'bbox': None,
                            'fallbacks': ['europe'],
                            'grid_origin': (1.25, 1.25),
                            'default_resolution': 2.5,
                            'instead_without_data': None,
                            'local_crs': 'utm_crs',
                            'ortho': 'italy/bz-ortho/2023',
                            'credits': ['DTM / DSM 2.5 m (Autonomous Province of Bolzano - South Tyrol)'],
                            'nmt': {'class': 'WcsTiles',
                               'description': 'DTM 2.5 m (terrain) South Tyrol',
                               'folder': 'italy/bz-dtm/2.5m',
                               'prefix': None,
                               'native_res': 2.5,
                               'processing': 1,
                               'ttl_days': None,
                               'credit': 'DTM / DSM 2.5 m (Autonomous Province of Bolzano - South Tyrol)',
                               'shift': (0.0, 0.0),
                               'url': 'https://geoservices9.civis.bz.it/geoserver/ows',
                               'coverage': 'p_bz-Elevation__DigitalTerrainModel-2.5m',
                               'crs': 'EPSG:25832',
                               'axes': ('E', 'N'),
                               'fmt': 'image/tiff',
                               'fetch_res': 2.5,
                               'tile_px': 2000},
                            'nmpt': {'class': 'WcsTiles',
                               'description': 'DSM 2.5 m (trees, buildings) South Tyrol',
                               'folder': 'italy/bz-dsm/2.5m',
                               'prefix': None,
                               'native_res': 2.5,
                               'processing': 1,
                               'ttl_days': None,
                               'credit': 'DTM / DSM 2.5 m (Autonomous Province of Bolzano - South Tyrol)',
                               'shift': (0.0, 0.0),
                               'url': 'https://geoservices9.civis.bz.it/geoserver/ows',
                               'coverage': 'p_bz-Elevation__DigitalElevationModel-2.5m',
                               'crs': 'EPSG:25832',
                               'axes': ('E', 'N'),
                               'fmt': 'image/tiff',
                               'fetch_res': 2.5,
                               'tile_px': 2000}},
            'luxembourg': {'crs': 'EPSG:2169',
                           'countries': ('lu',),
                           'bbox': None,
                           'fallbacks': ['europe'],
                           'grid_origin': (0.0, 0.0),
                           'default_resolution': 1.0,
                           'instead_without_data': None,
                           'local_crs': 'utm_crs',
                           'ortho': 'luxembourg/ortho/live',
                           'credits': ['BD-L-Lidar2024 MNT / MNS 0.5 m (ACT, Luxembourg)'],
                           'nmt': {'class': 'FileBlocks',
                                 'description': 'Lidar 2024 MNT 0.5 m (terrain)',
                                 'folder': 'luxembourg/lidar2024-mnt/20241223',
                                 'prefix': None,
                                 'native_res': 0.5,
                                 'processing': 1,
                                 'ttl_days': None,
                                 'credit': 'BD-L-Lidar2024 MNT / MNS 0.5 m (ACT, Luxembourg)',
                                 'shift': (0.0, 0.0)},
                           'nmpt': {'class': 'FileBlocks',
                                 'description': 'Lidar 2024 MNS 0.5 m (trees, buildings)',
                                 'folder': 'luxembourg/lidar2024-mns/20241223',
                                 'prefix': None,
                                 'native_res': 0.5,
                                 'processing': 1,
                                 'ttl_days': None,
                                 'credit': 'BD-L-Lidar2024 MNT / MNS 0.5 m (ACT, Luxembourg)',
                                 'shift': (0.0, 0.0)}},
            'denmark': {'crs': 'EPSG:25832',
                        'countries': ('dk',),
                        'bbox': None,
                        'fallbacks': ['europe'],
                        'grid_origin': (0.0, 0.0),
                        'default_resolution': 1.0,
                        'instead_without_data': None,
                        'local_crs': 'utm_crs',
                        'ortho': None,
                        'credits': ['Danmarks Højdemodel, DHM/Terræn and DHM/Overflade (Klimadatastyrelsen)'],
                        'nmt': {'class': 'WcsTiles',
                                'description': 'DHM/Terraen 0.4 m (terrain)',
                                'folder': 'denmark/dhm-terraen/live',
                                'prefix': None,
                                'native_res': 0.4,
                                'processing': 1,
                                'ttl_days': 730,
                                'credit': 'Danmarks Højdemodel, DHM/Terræn and DHM/Overflade (Klimadatastyrelsen)',
                                'shift': (0.0, 0.0),
                                'url': 'https://wcs.datafordeler.dk/DHMNedboer/dhm_wcs/1.0.0/WCS',
                                'coverage': 'dhm_terraen',
                                'crs': 'EPSG:25832',
                                'axes': ('x', 'y'),
                                'fmt': 'GTiff',
                                'fetch_res': None,
                                'tile_px': 2000},
                        'nmpt': {'class': 'WcsTiles',
                                 'description': 'DHM/Overflade 0.4 m (trees, buildings)',
                                 'folder': 'denmark/dhm-overflade/live',
                                 'prefix': None,
                                 'native_res': 0.4,
                                 'processing': 1,
                                 'ttl_days': 730,
                                 'credit': 'Danmarks Højdemodel, DHM/Terræn and DHM/Overflade (Klimadatastyrelsen)',
                                 'shift': (0.0, 0.0),
                                 'url': 'https://wcs.datafordeler.dk/DHMNedboer/dhm_wcs/1.0.0/WCS',
                                 'coverage': 'dhm_overflade',
                                 'crs': 'EPSG:25832',
                                 'axes': ('x', 'y'),
                                 'fmt': 'GTiff',
                                 'fetch_res': None,
                                 'tile_px': 2000}},
            'finland': {'crs': 'EPSG:3067',
                        'countries': ('fi', 'ax'),
                        'bbox': None,
                        'fallbacks': ['europe'],
                        'grid_origin': (0.0, 0.0),
                        'default_resolution': 2.0,
                        'instead_without_data': None,
                        'local_crs': 'utm_crs',
                        'ortho': None,
                        'credits': ['Elevation model 2 m (National Land Survey of Finland)'],
                        'nmt': {'class': 'FileBlocks',
                                'description': 'NLS elevation model 2 m (terrain)',
                                'folder': 'finland/dem2m/live',
                                'prefix': None,
                                'native_res': 2.0,
                                'processing': 1,
                                'ttl_days': 730,
                                'credit': 'Elevation model 2 m (National Land Survey of Finland)',
                                'shift': (0.0, 0.0)},
                        'nmpt': None},
            'europe': {'crs': None,
                       'countries': (),
                       'bbox': None,
                       'fallbacks': [],
                       'grid_origin': (0.0, 0.0),
                       'default_resolution': 30.0,
                       'instead_without_data': None,
                       'local_crs': 'utm_crs',
                       'ortho': None,
                       'credits': ['FABDEM V1-2', 'Copernicus DEM GLO-30'],
                       'nmt': {'class': 'DegreeTiles',
                               'description': 'FABDEM (terrain)',
                               'folder': 'fabdem/v1-2',
                               'prefix': None,
                               'native_res': 30,
                               'processing': 1,
                               'ttl_days': None,
                               'credit': 'FABDEM V1-2',
                               'shift': (0.0, 0.0)},
                       'nmpt': {'class': 'DegreeTiles',
                                'description': 'Copernicus DEM GLO-30 (surface)',
                                'folder': 'copernicus30/2021/dem',
                                'prefix': None,
                                'native_res': 30,
                                'processing': 1,
                                'ttl_days': None,
                                'credit': 'Copernicus DEM GLO-30',
                                'shift': (0.0, 0.0)}},
            'nasadem': {'crs': None,
                        'countries': (),
                        'bbox': None,
                        'fallbacks': ['europe'],
                        'grid_origin': (0.0, 0.0),
                        'default_resolution': 30.0,
                        'instead_without_data': None,
                        'local_crs': 'utm_crs',
                        'ortho': None,
                        'credits': ['NASADEM'],
                        'nmt': {'class': 'OpenTopographyTiles',
                                'description': 'NASADEM',
                                'folder': 'nasadem/v1',
                                'prefix': None,
                                'native_res': 30,
                                'processing': 1,
                                'ttl_days': None,
                                'credit': 'NASADEM',
                                'shift': (0.0, 0.0)},
                        'nmpt': None},
            'WATER_MASK': {'class': 'DegreeTiles',
                           'description': 'Copernicus water body mask',
                           'folder': 'copernicus30/2021/wbm',
                           'prefix': None,
                           'native_res': 30,
                           'processing': 1,
                           'ttl_days': None,
                           'credit': 'Copernicus DEM GLO-30 water body mask',
                           'shift': (0.0, 0.0)}}


def _layer(layer):
    info = {"class": type(layer).__name__, "description": layer.description, "folder": layer.folder,
            "prefix": getattr(layer, "prefix", None), "native_res": layer.native_res,
            "processing": layer.processing, "ttl_days": layer.ttl_days,
            "credit": layer.credit.data if layer.credit else None, "shift": layer.shift}
    if isinstance(layer, src.WcsTiles):
        info.update(url=layer.url, coverage=layer.coverage, crs=layer.crs, axes=layer.axes, fmt=layer.fmt,
                    fetch_res=layer.fetch_res, tile_px=layer.tile_px)
    if isinstance(layer, src.IndexedTiles):
        info.update(index_url=layer.index_url)
    return info


def test_source_order():
    assert list(src.SOURCES) == IDS


def test_declarations():
    found = {}
    for sid, s in src.SOURCES.items():
        found[sid] = {"crs": s.crs, "countries": s.countries, "bbox": s.bbox, "fallbacks": s.fallbacks,
                      "grid_origin": s.grid_origin, "default_resolution": s.default_resolution,
                      "instead_without_data": s.instead_without_data, "local_crs": s.local_crs.__name__,
                      "ortho": s.ortho.folder if s.ortho else None,
                      "credits": [c.data for c in s.credits],
                      "nmt": _layer(s.nmt), "nmpt": _layer(s.nmpt) if s.nmpt else None}
    found["WATER_MASK"] = _layer(src.WATER_MASK)
    for key in DECLARED:
        assert found[key] == DECLARED[key], key
    assert list(found) == list(DECLARED)


SHEET = dict(year=2023, name="77532_1356765_M-34-64-D-a-1-1", godlo="M-34-64-D-a-1-1", url="https://example/a.asc",
             crs="EPSG:2180", res=1.0)
STAC = dict(year=2025, name="26000-12000", godlo="26000-12000", url="https://example/b.tif", crs="EPSG:2056", res=2.0)
LGLN = dict(year=2018, name="599-5748", godlo="599-5748/1m", url="https://example/c.tif", crs="EPSG:25832", res=1.0)
BLOCK = dict(crs="EPSG:26913", i=532, j=4211, size=1000.0, year=2020, key="ab12cd34")
# (source, layer, tile, its path in the cache, what tile_of gives for that path)
PATHS = [
    ("malta", "nmt", (1.0, 3, -2), "malta/dtm/2018/epsg32633-1m-2000px-tif/3_-2.tif", (1.0, 3, -2)),
    ("malta2012", "nmpt", (1.0, -1, 0), "malta/dsm/2012/epsg25833-1m-2000px-tif/-1_0.tif", (1.0, -1, 0)),
    ("spain", "nmt", (5.0, 10, 20), "spain/mdt05/live/epsg25830-5m-2000px-asc/10_20.tif", (5.0, 10, 20)),
    ("spain_canarias", "nmpt", (5.0, -3, 7), "spain/mds05/live/epsg25830-5m-2000px-asc/-3_7.tif", (5.0, -3, 7)),
    ("slovakia", "nmt", (-287, -612), "slovakia/dmr5/5.0/epsg8353-1m-2km/-29_-62/-287_-612.tif", None),
    ("slovakia", "nmpt", (-301, -598), "slovakia/dmp1/1.0/epsg8353-1m-2km/-31_-60/-301_-598.tif", None),
    ("europe", "nmt", (50, 19), "fabdem/v1-2/N50E019.tif", None),
    ("europe", "nmpt", (-34, -71), "copernicus30/2021/dem/S34W071.tif", None),
    ("nasadem", "nmt", (46, 7), "nasadem/v1/N46E007.tif", None),
    ("geoportal", "nmt", "sheet", "poland/nmt/2023_77532_1356765_M-34-64-D-a-1-1.tif", None),
    ("geoportal", "nmpt", "sheet", "poland/nmpt/2023_77532_1356765_M-34-64-D-a-1-1.tif", None),
    ("swisstopo", "nmt", "stac", "switzerland/swissalti3d/2m/2025_26000-12000.tif", None),
    ("swisstopo", "nmpt", "stac", "switzerland/swisssurface3d/2m/2025_26000-12000.tif", None),
    ("usa", "nmt", "block", "usa/3dep-1m/epsg26913/53_421/2020_532_4211_ab12cd34.tif", None),
    ("alaska_ifsar", "nmt", "block", "usa/ifsar-5m/epsg26913/53_421/2020_532_4211_ab12cd34.tif", None),
    ("usgs10m", "nmt", (-1195, 375), "usa/3dep-13/live/n38w120/-1195_375.tif", (-1195, 375)),
    ("austria", "nmt", (4420, 2685), "austria/als-dtm/20250915/88_53/4420_2685.tif", (4420, 2685)),
    ("austria", "nmpt", (4420, 2685), "austria/als-dsm/20250915/88_53/4420_2685.tif", (4420, 2685)),
    ("wales", "nmt", (262, 356), "wales/lidar-dtm/20241004/5_7/262_356.tif", (262, 356)),
    ("wales", "nmpt", (262, 356), "wales/lidar-dsm/20241004/5_7/262_356.tif", (262, 356)),
    ("england", "nmt", (1.0, 211, 192), "england/lidar-composite-dtm/2022/epsg27700-1m-2000px-tif/211_192.tif",
     (1.0, 211, 192)),
    ("england", "nmpt", (1.0, 211, 192), "england/lidar-composite-dsm/2022/epsg27700-1m-2000px-tif/211_192.tif",
     (1.0, 211, 192)),
    ("hesse", "nmt", (1.0, 251, 2835), "hesse/dgm1/live/epsg25832-1m-2000px-tif/251_2835.tif", (1.0, 251, 2835)),
    ("hesse", "nmpt", (1.0, 251, 2835), "hesse/dom1/live/epsg25832-1m-2000px-tif/251_2835.tif", (1.0, 251, 2835)),
    ("mecklenburg_vorpommern", "nmt", (1.0, 206, 3024),
     "mecklenburg_vorpommern/dgm1/live/epsg25833-1m-2000px-tif/206_3024.tif", (1.0, 206, 3024)),
    ("mecklenburg_vorpommern", "nmpt", (1.0, 206, 3024),
     "mecklenburg_vorpommern/dom1/live/epsg25833-1m-2000px-tif/206_3024.tif", (1.0, 206, 3024)),
    ("saxony_anhalt", "nmt", (1.0, 320, 2866), "saxony_anhalt/dgm1/live/epsg25832-1m-2000px-tif/320_2866.tif",
     (1.0, 320, 2866)),
    ("saxony_anhalt", "nmpt", (1.0, 320, 2866), "saxony_anhalt/dom1/live/epsg25832-1m-2000px-tif/320_2866.tif",
     (1.0, 320, 2866)),
    ("lower_saxony", "nmt", "lgln", "lower_saxony/dgm1/live/1m/2018_599-5748.tif", None),
    ("lower_saxony", "nmpt", "lgln", "lower_saxony/dom1/live/1m/2018_599-5748.tif", None),
    ("south_tyrol", "nmt", (2.5, 142, 1031), "italy/bz-dtm/2.5m/epsg25832-2.5m-2000px-tif-o1.25_1.25-e3/142_1031.tif",
     (2.5, 142, 1031)),
    ("south_tyrol", "nmpt", (2.5, 142, 1030), "italy/bz-dsm/2.5m/epsg25832-2.5m-2000px-tif-o1.25_1.25-e3/142_1030.tif",
     (2.5, 142, 1030)),
    ("luxembourg", "nmt", (92, 98), "luxembourg/lidar2024-mnt/20241223/1_1/92_98.tif", (92, 98)),
    ("luxembourg", "nmpt", (92, 98), "luxembourg/lidar2024-mns/20241223/1_1/92_98.tif", (92, 98)),
    ("denmark", "nmt", (1.0, 352, 3048), "denmark/dhm-terraen/live/epsg25832-1m-2000px-tif/352_3048.tif",
     (1.0, 352, 3048)),
    ("denmark", "nmpt", (1.0, 352, 3048), "denmark/dhm-overflade/live/epsg25832-1m-2000px-tif/352_3048.tif",
     (1.0, 352, 3048)),
    ("finland", "nmt", (261, 3669), "finland/dem2m/live/5_73/261_3669.tif", (261, 3669)),
]


@pytest.mark.parametrize("sid, kind, tile, path, tile_of", PATHS)
def test_tile_paths(tmp_path, sid, kind, tile, path, tile_of):
    tile = {"sheet": lambda: src.Sheet(**SHEET), "stac": lambda: src.Sheet(**STAC),
            "lgln": lambda: src.Sheet(**LGLN),
            "block": lambda: src.Block(**BLOCK)}.get(tile, lambda: tile)()
    layer = getattr(src.SOURCES[sid], kind)
    cache_dir = str(tmp_path)
    assert os.path.relpath(layer.tile_path(cache_dir, tile), cache_dir).replace(os.sep, "/") == path
    assert layer.tile_of(path) == tile_of
    assert layer.tile_of("elsewhere/" + path) is None


def test_water_mask_and_tile_urls(tmp_path):
    mask = src.WATER_MASK
    assert (os.path.relpath(mask.tile_path(str(tmp_path), (36, 14)), tmp_path).replace(os.sep, "/")
            == "copernicus30/2021/wbm/N36E014.tif")
    copernicus = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_"
    fabdem = "https://huggingface.co/buckets/links-ads/fabdem/resolve/tiles/"
    assert mask.tile_url((36, 14)) == copernicus + "N36_00_E014_00_DEM/AUXFILES/Copernicus_DSM_COG_10_N36_00_E014_00_WBM.tif"
    europe, usgs10m = src.SOURCES["europe"], src.SOURCES["usgs10m"]
    assert europe.nmt.tile_url((50, 19)) == fabdem + "N50E010-N60E020_FABDEM_V1-2/N50E019_FABDEM_V1-2.tif"
    assert europe.nmt.tile_url((-34, -71)) == fabdem + "S40W080-S30W070_FABDEM_V1-2/S34W071_FABDEM_V1-2.tif"
    assert europe.nmpt.tile_url((50, 19)) == copernicus + "N50_00_E019_00_DEM/Copernicus_DSM_COG_10_N50_00_E019_00_DEM.tif"
    assert (europe.nmpt.tile_url((-34, -71))
            == copernicus + "S34_00_W071_00_DEM/Copernicus_DSM_COG_10_S34_00_W071_00_DEM.tif")
    assert (usgs10m.nmt.tile_url((-1195, 375))
            == "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/n38w120/USGS_13_n38w120.tif")


@pytest.mark.parametrize("sid, kind, lat, lon, path", [
    ("geoportal", "nmt", 50.15, 19.75, "poland/sheet-index/SkorowidzNMT/N50.15_E019.75.json"),
    ("geoportal", "nmpt", 50.15, 19.75, "poland/sheet-index/SkorowidzNMPT/N50.15_E019.75.json"),
    ("swisstopo", "nmt", 46.59, 7.91, "switzerland/sheet-index/ch.swisstopo.swissalti3d/N46.59_E007.91.json"),
    ("usa", "nmt", 37.7, -119.6, "usa/sheet-index/dem1m/N37.70_W119.60.json"),
    ("lower_saxony", "nmpt", 51.88, 10.44, "lower_saxony/sheet-index/dom1/N51.88_E010.44.json"),
    ("alaska_ifsar", "nmt", 61.2, -149.9, "usa/sheet-index/ifsar5m/N61.20_W149.90.json"),
])
def test_index_paths(tmp_path, sid, kind, lat, lon, path):
    layer = getattr(src.SOURCES[sid], kind)
    assert os.path.relpath(layer.index_path(str(tmp_path), lat, lon), tmp_path).replace(os.sep, "/") == path


LAYER_METHODS = ["tiles", "tile_path", "bytes_per_tile", "missing", "estimate", "download_tile", "download",
                 "to_download", "downloaded", "tile_url", "unavailable", "tile_of", "has_data_near",
                 "_download_and_record", "source_date", "files", "used"]
LAYER_ATTRIBUTES = ["description", "folder", "native_res", "credit", "shift", "processing", "ttl_days"]


def test_layer_surface():
    """What search.py, update.py, mosaics and runs use of a layer: every layer keeps it."""
    layers = [layer for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt) if layer] + [src.WATER_MASK]
    for layer in layers:
        for name in LAYER_METHODS:
            assert callable(getattr(layer, name)), (layer.description, name)
        for name in LAYER_ATTRIBUTES:
            assert hasattr(layer, name), (layer.description, name)
        if isinstance(layer, src.WcsTiles):
            for name in ("url", "coverage", "crs", "axes", "fmt", "fetch_res", "tile_px"):
                assert hasattr(layer, name), (layer.description, name)
            assert callable(layer.bounds_wgs84)
        if isinstance(layer, src.IndexedTiles):
            assert isinstance(layer.index_url, str) and isinstance(layer.prefix, str)
            assert callable(layer.index_path) and callable(layer.update_index_tile)
    # The relations search.py (WcsTiles, OpenTopographyTiles) and update.py (IndexedTiles) rely on
    indexed = {sid for sid, s in src.SOURCES.items() if isinstance(s.nmt, src.IndexedTiles)}
    assert indexed == {"geoportal", "swisstopo", "alaska", "alaska_ifsar", "usa", "lower_saxony"}
    wcs = {sid for sid, s in src.SOURCES.items() if isinstance(s.nmt, src.WcsTiles)}
    assert wcs == {"malta", "malta2012", "spain_canarias", "spain", "england", "hesse", "mecklenburg_vorpommern",
                   "saxony_anhalt", "south_tyrol", "denmark"}
    assert isinstance(src.SOURCES["nasadem"].nmt, src.OpenTopographyTiles)
    assert issubclass(src.OpenTopographyTiles, src.DegreeTiles)
    for cls in (src.SheetTiles, src.StacTiles, src.TnmBlocks, src.Usgs1mBlocks, src.IfsarBlocks):
        assert issubclass(cls, src.IndexedTiles)
    for cls in (src.WcsTiles, src.GridTiles, src.DegreeTiles, src.DegreeBlocks, src.FileLayer, src.IndexedTiles):
        assert issubclass(cls, src.Layer)
    assert not issubclass(src.DegreeBlocks, src.IndexedTiles)


# A copy of the offline boxes of 2026-10-31: the order matters (the first box holding a point wins)
ALASKA = (51.0, 71.5, -180.0, -129.9)
BOXES = [("mt", (35.78, 36.10, 14.15, 14.60)), ("pl", (49.0, 54.9, 14.1, 24.2)),
         ("es", (27.0, 43.9, -18.6, 4.4)), ("sk", (47.7, 49.65, 16.8, 22.6)),
         ("ch", (45.8, 47.85, 5.9, 10.5)), ("us", (24.4, 49.4, -125.0, -66.9)), ("us", ALASKA),
         ("pr", (17.8, 18.6, -67.4, -65.2)), ("at", (46.37, 49.02, 9.53, 17.17)),
         ("gb-wls", (51.33, 53.45, -5.35, -2.64)), ("gb-eng", (49.85, 55.82, -5.75, 1.77)),
         ("de-he", (49.39, 51.66, 7.77, 10.24)), ("de-mv", (53.1, 54.7, 10.59, 14.42)),
         ("de-st", (50.94, 53.05, 10.56, 13.19)), ("de-ni", (51.29, 53.9, 6.65, 11.6)),
         ("it-bz", (46.21, 47.10, 10.38, 12.48)), ("lu", (49.44, 50.19, 5.73, 6.54)),
         ("dk", (54.90, 57.76, 8.07, 12.70)), ("dk", (54.56, 54.90, 10.15, 12.70)), ("dk", (54.98, 55.32, 14.68, 15.21)),
         ("fi", (59.7, 70.1, 19.3, 31.6))]


def test_country_code_offline(monkeypatch, tmp_path):
    """Offline (the lookup fails), the country comes from the rough boxes: the same answers on a
    0.05° lattice over every box and a little beyond."""
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    country_code = src.choose.country_code
    cache_dir = str(tmp_path)
    checked = 0
    for _, (s, n, w, e) in BOXES:
        for a in range(round((s - 0.1) * 20), round((n + 0.1) * 20) + 1):
            lat = a / 20
            for b in range(round((w - 0.1) * 20), round((e + 0.1) * 20) + 1):
                lon = b / 20
                expected = next((code.split("-")[0] for code, (s2, n2, w2, e2) in BOXES
                                 if s2 <= lat <= n2 and w2 <= lon <= e2), None)
                assert country_code(lat, lon, cache_dir) == expected, (lat, lon)
                checked += 1
    assert checked > 100_000


def test_listing_offline_and_sample():
    """Every source has its row of README's table; its offline boxes name its own countries (or
    regions, for a source with regions), and its
    sample point (the probe's and tools/check_source.py's) lies where the source is used."""
    assert sorted(src.OFFLINE_BOXES) == sorted(BOXES)
    for sid, s in src.SOURCES.items():
        assert s.listing is not None and s.listing.where and s.listing.terrain, sid
        for region in s.regions:  # ISO 3166-2 in lower case, of its countries
            assert region == region.lower() and region.split("-")[0] in s.countries, (sid, region)
        for code, _ in s.offline:  # a region's box (gb-wls) for a source with regions
            assert code in (s.regions or s.countries), (sid, code)
        if s.sample is None:
            assert sid == "alaska"  # no 1 m DEM in Alaska yet
            continue
        lat, lon = s.sample
        assert s.covers(lat, lon), sid
        if s.offline:
            assert any(south <= lat <= north and west <= lon <= east
                       for _, (south, north, west, east) in s.offline), sid


# Names tests and tools patch, each in one module only: patched there, they take effect for every
# caller (the code calls them through their module: net._get(...)); on the package itself such a
# patch would fail loudly instead of silently missing the code
PATCHED = {"_get": "net", "_sleep": "net", "DOWNLOAD_THREADS": "layer", "country_code": "choose"}


def test_patched_names_have_one_home():
    import importlib
    for name, module in PATCHED.items():
        assert hasattr(importlib.import_module(f"sources.{module}"), name), (module, name)
        assert not hasattr(src, name), name


def test_patched_names_are_never_imported_by_name():
    """`from .net import _get` would bind a copy that a patch of net._get never reaches."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [os.path.join(folder, f) for folder, _, files in os.walk(os.path.join(root, "sources"))
             for f in files if f.endswith(".py")]
    paths += [os.path.join(root, d, f) for d in ("", "tests", "tools") for f in os.listdir(os.path.join(root, d))
              if f.endswith(".py")]
    for path in paths:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.level or (node.module or "").startswith("sources")):
                named = {alias.name for alias in node.names} & set(PATCHED)
                assert not named, f"{os.path.relpath(path, root)}:{node.lineno} imports {named} by name"


def _homes():
    """The one module of the package that defines each top-level name."""
    import ast
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sources")
    homes = {}
    for folder, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".py") or f == "__init__.py" and folder == root:
                continue
            path = os.path.relpath(os.path.join(folder, f), root)[:-3].replace(os.sep, ".")
            module = "sources." + path.removesuffix(".__init__").removesuffix("__init__").rstrip(".")
            with open(os.path.join(folder, f), encoding="utf-8") as file:
                tree = ast.parse(file.read())
            for node in tree.body:
                targets = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
                names = [node.name] if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else \
                    [n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)]
                for name in names:
                    if name == "SOURCES" and module.startswith("sources.catalogue."):
                        continue  # a family's own list, joined in sources.catalogue.SOURCES
                    assert homes.get(name, module) == module, (name, homes[name], module)
                    homes[name] = module
    return homes


def test_exports_are_the_objects_of_their_modules():
    import importlib
    homes = _homes()
    assert len(set(src.__all__)) == len(src.__all__)
    for name in src.__all__:
        assert getattr(src, name) is getattr(importlib.import_module(homes[name]), name), name


def test_docs_list_every_source():
    """README's "Data sources" table and the ids of --source are generated from the catalogue:
    run `uv run tools/source_docs.py` after changing a source."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import source_docs
    with open(os.path.join(REPO, "README.md"), encoding="utf-8") as f:
        text = f.read()
    assert source_docs.render(text) == text, "README.md is out of date: run `uv run tools/source_docs.py`"
    for sid in src.SOURCES:
        assert f"| `{sid}` |" in text and f"`{sid}`" in source_docs.ids()


# The wording each provider's terms ask for (the audit of 2026-11-01): a change needs its terms read again
ATTRIBUTIONS = {
    "slovakia": "© ÚGKK SR",
    "malta": "Planning Authority, Malta: Digital Terrain / Surface Model 2018, CC BY 4.0",
    "malta2012": "Planning Authority, Malta: Digital Terrain / Surface Model 2012, CC BY 4.0",
    "spain": "Obra derivada de MDT05-cob1 2008-2015 y MDS05 2008-2015 CC-BY 4.0 scne.es",
    "spain_canarias": "Obra derivada de MDT05-cob1 2008-2015 y MDS05 2008-2015 CC-BY 4.0 scne.es",
    "saxony_anhalt": "© GeoBasis-DE / LVermGeo ST, Daten geändert",
    "mecklenburg_vorpommern": "© GeoBasis-DE/M-V {year}, Daten geändert",
    "finland": "Contains data from the National Land Survey of Finland Elevation model 2 m {year}, CC BY 4.0, processed",
    "wales": "Contains public sector information licensed under the Open Government Licence v3.0",
    "england": "© Environment Agency copyright and/or database right 2022. All rights reserved. Modified: resampled "
               "onto the working grid.",
    "usa": "USGS 3D Elevation Program (3DEP). Map services and data available from U.S. Geological Survey, "
           "National Geospatial Program.",
}
ORTHOS = {  # source: (attribution, attribution_url)
    "austria": ("Datenquelle: basemap.at", "https://basemap.at"),
    "slovakia": ("© GKÚ Bratislava, NLC, CC BY 4.0", src.CC_BY[1]),
    "malta": ("Orthoimagery 2018: Planning Authority, Malta, CC BY 4.0", src.CC_BY[1]),
    "spain": ("PNOA CC-BY 4.0 scne.es", src.CC_BY[1]),
    "south_tyrol": ("Orthofoto 2023: Autonome Provinz Bozen - Südtirol (CC BY 4.0)", src.CC_BY[1]),
    "saxony_anhalt": ("© GeoBasis-DE / LVermGeo ST, dl-de/by-2-0", "https://www.govdata.de/dl-de/by-2-0"),
    "lower_saxony": ("LGLN ({year}), CC BY 4.0", src.CC_BY[1]),
    "mecklenburg_vorpommern": ("© GeoBasis-DE/M-V {year}, CC BY 4.0", src.CC_BY[1]),
    "geoportal": ("GUGiK", None),
}


def test_credit_wording():
    for sid, text in ATTRIBUTIONS.items():
        assert src.SOURCES[sid].credits[0].attribution == text, sid
    for sid, (text, url) in ORTHOS.items():
        ortho = src.SOURCES[sid].ortho
        assert (ortho.attribution, ortho.attribution_url) == (text, url), sid
    assert src.SOURCES["malta"].credits[0].url == "https://portal.data.gov.mt/dataset/digital-terrain-model-2018"
    assert "196 m south" in src.SOURCES["malta2012"].credits[0].notice
    assert "NSF Award Numbers 2410799, 2410800 & 2410801." in src.SOURCES["nasadem"].credits[0].notice
    assert "Modified:" in src.FABDEM_CREDIT.notice
    assert src.SOURCES["swisstopo"].credits[0].url == ("https://www.swisstopo.admin.ch/en/"
                                                       "terms-of-use-free-geodata-and-geoservices")
    assert "https://www.openstreetmap.org/fixthemap" in src.OSM_CREDIT.notice


def test_processed_note_with_every_run():
    """ATTRIBUTION.txt says that what a run made comes from changed data, after its credits."""
    import runs
    note = src.credit.PROCESSED_NOTE
    text = runs.attribution_text({"name": "x", "attribution": [src.FABDEM_CREDIT.as_dict()]})
    assert text.index(src.FABDEM_CREDIT.data) < text.index(note)
    assert note in runs.attribution_text({"name": "x", "source": {"id": "files", "description": "a.tif"}})
    assert note not in runs.attribution_text({"name": "x"})  # nothing recorded: nothing to say it of


def test_about_page_links_and_note():
    """The about page: orthophoto attributions as links where attribution_url is set (escaped, no script), the
    processed note, OSM's fixthemap link, no Esri (removed from the maps)."""
    import html
    import web
    page = web.about_page("someone@example.org")
    assert "<a href='https://basemap.at'>Datenquelle: basemap.at</a>" in page
    assert (f"<a href='{src.CC_BY[1]}'>{html.escape('© GKÚ Bratislava, NLC, CC BY 4.0')}</a>" in page)
    assert "<li>Orthophoto (geoportal.gov.pl): GUGiK</li>" in page  # no link: none set
    assert html.escape(src.credit.PROCESSED_NOTE) in page
    assert "href='https://www.openstreetmap.org/fixthemap'" in page
    assert "Esri" not in page and "<script" not in page
