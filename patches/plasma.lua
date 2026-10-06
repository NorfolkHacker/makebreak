local Plasma = AcidGame:extend("Plasma")
Plasma.TICK_MS = 40              -- 25 frames a second

local CELL = 4                   -- each "pixel" is a 4x4 block
local TOP = 16                   -- the title bar is 16px tall

function Plasma:on_create()
  self.w, self.h = acid_window_size()
  self.cx, self.cy = self.w // 2, self.h // 2   -- where the ripple starts
  self.t = 0
end

function Plasma:on_touch(x, y, pressed)
  if pressed then self.cx, self.cy = x, y end   -- drag the ripple about
end

function Plasma:on_tick()
  self.t = self.t + 0.08
  if not self:focused() then return end

  local t, cx, cy = self.t, self.cx, self.cy
  acid_begin_frame()
  acid_draw_window_frame(self:window_title())
  for y = TOP, self.h - 1, CELL do
    for x = 0, self.w - 1, CELL do
      -- the same four ripples as issue #00, stacked
      local v = math.sin(x * 0.04 + t)
              + math.sin(y * 0.03 - t)
              + math.sin((x + y) * 0.03 + t)
              + math.sin(math.sqrt((x - cx)^2 + (y - cy)^2) * 0.04 - t * 1.5)
      -- v runs from -4 to 4: turn it into a spot on the 256-colour wheel
      acid_fill_rect(x, y, CELL, CELL, AcidPalette.hue(math.floor(v * 32 + t * 20)))
    end
  end
  acid_draw_window_border()
  acid_end_frame()
end

Plasma:new():start()
