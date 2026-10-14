-- ────────────── Startup Applications ──────────────
-- See https://wiki.hypr.land/Configuring/Basics/Autostart/

-- hl.on("hyprland.start", function ()
--   hl.exec_cmd("kitty")
--   hl.exec_cmd("nm-applet")
--   hl.exec_cmd("waybar & hyprpaper & firefox")
-- end)

hl.on("hyprland.start", function ()
  -- Start the Noctalia v5 native shell
  hl.exec_cmd("noctalia")
end)
