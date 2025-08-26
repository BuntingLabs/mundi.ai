---
title: Uploading files to Mundi
description: Mundi supports .gpkg, .fgb, .geojson, shapefiles in .zip, .tif, .kml, .kmz, .laz, and .csv file uploads.
---

Mundi supports most vector and raster file formats. You can also upload CSV spreadsheets and LAS/LAZ point cloud files.

Drag and drop a file directly onto the map to upload it to Mundi. You can also click on `Add Layer Source` > `Upload file`
in the layer list to open the file browser.

![Uploading a GeoJSON file to Mundi when self-hosted](../../../assets/selfhost/upload.jpg)

Uploading files can also be done via [the Mundi developer API](/developer-api/operations/upload_layer_to_map/).

## Vector spatial data

Mundi supports FlatGeobuf (`.fgb`), GeoPackage (`.gpkg`), GeoJSON (`.geojson`), KML/KMZ (`.kml`, `.kmz`), and Shapefiles. Files in any CRS/projection
will work. Vector data is stored in its original CRS but is reprojected to Web Mercator (EPSG:3857) for display (tiles).

Other files supported by GDAL may work, but are not tested regularly. [Create a new issue](https://github.com/BuntingLabs/mundi.ai/issues/new)
to request a new file format.

### GeoPackage support

Currently, Mundi will load the first layer in a GeoPackage file, and does not import styles embedded from QGIS.
You will need to export the GeoPackage's individual layers to load them all.

### Shapefile support

To import a shapefile into Mundi, you should put the `.shp`, `.dbf`, `.shx`, and `.prj` files in a single ZIP archive
and then upload that to Mundi.

## Raster data

Mundi supports GeoTIFFs (`.tif` and `.tiff`, includes COGs) and DEM (`.dem`)files. Only single-band and RGB data is supported. Single-band data
will be assigned a color map from its min and max values. Raster data is stored in its original CRS.

## LAS/LAZ point clouds

Mundi supports `.las` and `.laz` point cloud uploads. Point clouds must have a CRS associated with them. Right now, point clouds
are loaded entirely into memory in the browser, so we highly recommend downsampling point clouds before uploading.

## Spreadsheets (CSV)

Mundi accepts `.csv` files where each row represents a point. Your CSV must have a header row with column names
that separate out latitude and longitude columns with coordinates in WGS84 / EPSG:4326.
[You can also connect directly to Google sheets](/getting-started/google-sheets/).

For example, this CSV would successfully upload to Mundi:

```csv
name,yelp_score,lat,lng
Beachside building,4.5,37.735482,-122.506563
Yacht Club,4.7,37.850417,-122.531423
```

### Supported column names

To detect and convert to spatial data, you must have latitude and longitude columns. The following column names are detected:

Latitude: `lat`, `latitude`, `y`, `Y`, `Latitude`, `LAT`, or `LATITUDE`

Longitude: `lon`, `longitude`, `lng`, `x`, `X`, `Longitude`, `LON`, or `LONGITUDE`

### Geocoding addresses

Mundi does not currently support geocoding addresses in uploaded CSV files. If you have tabular data, like Excel spreadsheets,
CSVs, etc., we recommend you use [geocodio](https://www.geocod.io/) or [geoapify](https://www.geoapify.com/tools/geocoding-online/)
to geocode the addresses first. This may require you to edit the headers in the resulting CSV so that `latitude` and `longitude`
columns exist.
