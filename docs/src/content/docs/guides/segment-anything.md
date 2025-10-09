---
title: Segment Anything for Geospatial Data
description: Run a segmentation model on imagery and traditional maps and export to vector data, all online.
---

You can access run Segment Anything [online in Mundi](https://app.mundi.ai/tools/segment-anything/airplanes) to extract polygons from aerial
imagery, satellite imagery, and traditional maps. These polygons are already processed
in Mundi to be downloadable as vector spatial data as a GeoJSON.

The Segment Anything tool available in Mundi uses Meta's Segment Anything Model. To
use the model, you just need to draw a bounding box around each object you want to 
segment. Once you have segmented everything, you can download the output as a GeoJSON.

You can access the Segment Anything tool online, and do not need to own a GPU or download
any model. You can upload any imagery you need to segment or use our catalogue of imagery. 
Using the Segment Anything tool requires a Mundi subscription, starting at $45/month. 
There are sample locations with imagery loaded you can evaluate on in Mundi.

![the Mundi Segment Anything tool with example imagery already segmented](../../../assets/segment-anything/segment-anything-bboxes.jpg) 

## Introduction to Segment Anything

Segment Anything is a foundation model from Meta AI that predicts object masks given simple 
prompts such as points or boxes. We adapt Segment Anything for geospatial workflows by 
supporting GeoTIFFs and satellite imagery as inputs so that the polygons are already 
georeferenced and supporting GeoJSON exports that you can add to any GIS platform such as Mundi. 

## Adding data to segment

You can upload your own GeoTIFF to the Segment Anything tool or work with our own 
catalogue of aerial imagery. Selecting your own region or adding your own imagery
requires a [Mundi Basic subscription](https://mundi.ai/pricing). If you first want to evaluate the Segment 
Anything model, you can try our free public examples. 

![upload options](../../../assets/segment-anything/upload-options.jpg)

:::note
If your maps are not yet georeferenced, try our [AI Georeferencer.](https://docs.mundi.ai/guides/ai-georeferencer-for-aerial-imagery/). 
:::

### Free public examples

You can evaluate the Segment Anything tool without a paid account using our sample
imagery of popular targets. We update this list as we create more examples. If you
want to evaluate our tool on anything specific, email sales@buntinglabs.com

1. [Detect Aircraft in Aerial Imagery](https://app.mundi.ai/tools/segment-anything/airplanes)

## How to run the Segment Anything tool  

Unlike other Segment Anything applications, there are no downloads needed to run 
Mundi's Segment Anything tool. You only need to find the imagery you want to segment, 
add your positive and negative points, and download your preferred result. 

Unlike other applications of Segment Anything, this tool requires creating a bounding
box around each target. We found that allowing the model to predict more targets leads 
to much noisier results, requiring more clean up time. 

### Select the bounding box tool

To begin creating a bounding box, you need to seelct this icon. It will turn light grey
when selected:

![the bounding box icon for the Segment Anything tool](../../../assets/segment-anything/bbox-button.jpg)

### Draw a bounding box around each target

Once the bounding box tool is active, you can begin to left click to create a bounding 
box. Make sure to keep the box close to your target. Once you are done, either
double left click or right click to save the box. Once you save a box, the model will
run. 

![an unsegmented bounding box](../../../assets/segment-anything/bbox-drawn-2.jpg)

### Save the output

Once you segment one target, you can either draw more boxes around more targets or 
download the polygons as a GeoJSON.

To download, select the **Download GeoJSON** button on the right side of the image. 

![the option menu for different segment outputs](../../../assets/segment-anything/download-geojson.jpg)