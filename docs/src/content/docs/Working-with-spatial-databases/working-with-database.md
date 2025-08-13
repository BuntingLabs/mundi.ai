---
title: Working with a Database in Mundi
description: Learn how to work with spatial databases once connected in Mundi.
---

# Working with a Database in Mundi

Once you've connected to a spatial database in Mundi, you can explore, analyze, and visualize your spatial data. This guide covers the essential workflows for working with database data.

## Database Explorer

After connecting to a database, Mundi automatically generates a comprehensive overview of your spatial data:

- **Table List** - Browse all available spatial tables and views
- **Schema Information** - View table structures and relationships
- **Spatial Metadata** - See coordinate reference systems and geometry types
- **Data Preview** - Sample the data in each table

## Loading Spatial Layers

### From Database Tables

1. Navigate to the **Database** section in the sidebar
2. Click on any spatial table to view its details
3. Use the **Load Layer** button to add it to your map
4. The layer will appear in your layer list with default styling

### Layer Properties

Each loaded layer includes:
- **Source Information** - Database connection and table details
- **Spatial Properties** - CRS, geometry type, and extent
- **Attribute Fields** - All available data columns
- **Styling Options** - Colors, symbols, and labels

## Spatial Analysis

### Querying Data

- **Attribute Queries** - Filter data by field values
- **Spatial Queries** - Find features by location or geometry
- **SQL Queries** - Write custom SQL for complex analysis

### Geoprocessing Tools

- **Buffer Analysis** - Create areas around features
- **Intersection** - Find overlapping geometries
- **Distance Calculations** - Measure spatial relationships
- **Spatial Joins** - Combine data based on location

## Data Management

### Editing Features

- **Add Features** - Create new spatial objects
- **Modify Geometry** - Edit existing features
- **Update Attributes** - Change feature properties
- **Delete Features** - Remove unwanted data

### Export Options

- **Vector Formats** - GeoJSON, Shapefile, KML
- **Raster Formats** - GeoTIFF, PNG, JPEG
- **Database Export** - Save to new tables or databases

## Performance Optimization

### Large Datasets

- **Spatial Indexing** - Ensure your database has proper spatial indexes
- **Viewport Loading** - Load only visible data for better performance
- **Layer Filtering** - Use filters to reduce data volume
- **Caching** - Mundi caches frequently accessed data

### Best Practices

- Keep database connections stable
- Use appropriate coordinate reference systems
- Regularly update spatial indexes
- Monitor query performance

## Troubleshooting

### Common Issues

- **Slow Loading** - Check database performance and network
- **Missing Data** - Verify table permissions and spatial columns
- **Styling Problems** - Check coordinate reference system compatibility
- **Connection Errors** - Verify database status and credentials

### Getting Help

- Check the database connection status
- Review error messages in the console
- Consult the troubleshooting guides
- Reach out to the Mundi community 