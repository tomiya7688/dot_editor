from pixel_layers import LayeredPixelCanvas

layers = LayeredPixelCanvas(4)
layers.add_layer("人物")
layers.paint(1, 1, (255, 0, 0, 255))
layers.select_layer("背景")
layers.paint(0, 0, (0, 0, 30, 255))
composite = layers.composite()
assert composite.getpixel((0, 0)) == (0, 0, 30, 255)
assert composite.getpixel((1, 1)) == (255, 0, 0, 255)
restored_layers = LayeredPixelCanvas.from_source(layers.to_source())
assert set(restored_layers.layers) == {"背景", "人物"}
assert restored_layers.composite().getpixel((1, 1)) == (255, 0, 0, 255)
print("layer backend ok")
