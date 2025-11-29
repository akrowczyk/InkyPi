import logging
import time
import datetime
import yfinance as yf
from PIL import Image, ImageDraw, ImageFont
from plugins.base_plugin.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

class Stock(BasePlugin):
    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)
        self.retries = 3
        self.retry_delay = 5

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        # Add any dynamic template variables here if needed
        return template_params

    def get_stock_data(self, ticker, period, interval):
        """Fetches price and history from Yahoo Finance with retries"""
        for attempt in range(self.retries):
            try:
                stock = yf.Ticker(ticker)

                # fast_info is reliable on Pi
                current_price = stock.fast_info.last_price
                prev_close = stock.fast_info.previous_close

                # Fetch history
                hist = stock.history(period=period, interval=interval)

                try:
                    info = stock.info
                    d_open = info.get('open', 0.0)
                    d_high = info.get('dayHigh', 0.0)
                    d_low = info.get('dayLow', 0.0)
                    d_vol = info.get('volume', 0)
                except:
                    d_open = hist['Open'].iloc[-1] if not hist.empty else 0.0
                    d_high = hist['High'].max() if not hist.empty else 0.0
                    d_low = hist['Low'].min() if not hist.empty else 0.0
                    d_vol = hist['Volume'].sum() if not hist.empty else 0

                return {
                    "price": current_price,
                    "prev_close": prev_close,
                    "open": d_open,
                    "high": d_high,
                    "low": d_low,
                    "volume": d_vol,
                    "history": hist['Close'].tolist()
                }
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{self.retries} failed: {e}")
                time.sleep(self.retry_delay)

        return None

    def map_range(self, value, in_min, in_max, out_min, out_max):
        if in_max == in_min:
            return (out_min + out_max) / 2
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def generate_image(self, settings, device_config):
        ticker = settings.get("ticker", "TSLA")
        period = settings.get("period", "1d")
        interval = settings.get("interval", "15m")

        logger.info(f"Fetching data for {ticker}...")
        data = self.get_stock_data(ticker, period, interval)
        
        # Get dimensions correctly
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions
        
        # Colors
        c_bg = (255, 255, 255) # White
        c_text_main = (0, 0, 0) # Black
        c_dim = (0, 0, 0) # Black
        c_grid = (0, 0, 255) # Blue
        c_up = (0, 255, 0) # Green
        c_down = (255, 0, 0) # Red

        image = Image.new("RGB", (width, height), c_bg)
        draw = ImageDraw.Draw(image)
        
        if not data:
            logger.error("Failed to fetch data.")
            # Draw error message
            try:
                font_error = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(height * 0.08))
            except OSError:
                font_error = ImageFont.load_default()
            draw.text((20, height // 2), f"Failed to fetch data for {ticker}", fill=c_down, font=font_error)
            return image

        current_price = data['price']
        prev_close = data['prev_close']
        change_amt = current_price - prev_close
        change_pct = (change_amt / prev_close) * 100 if prev_close else 0

        # Determine Theme Colors
        is_bullish = change_amt >= 0
        c_accent = c_up if is_bullish else c_down

        # Fonts - Scale based on height
        font_path_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font_path_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

        try:
            font_giant = ImageFont.truetype(font_path_bold, int(height * 0.20)) # 100/480 ~= 0.2
            font_large = ImageFont.truetype(font_path_bold, int(height * 0.125)) # 60/480 ~= 0.125
            font_med = ImageFont.truetype(font_path_reg, int(height * 0.06)) # 30/480 ~= 0.06
            font_small = ImageFont.truetype(font_path_reg, int(height * 0.04)) # 20/480 ~= 0.04
            font_tiny = ImageFont.truetype(font_path_reg, int(height * 0.033)) # 16/480 ~= 0.033
        except OSError:
            # Fallback if fonts are missing
            font_giant = font_large = font_med = font_small = font_tiny = ImageFont.load_default()

        # 5. DRAW UI

        # Margins
        margin_x = int(width * 0.025)
        margin_y = int(height * 0.04)

        # -- HEADER --
        draw.text((margin_x, margin_y), ticker, fill=c_text_main, font=font_large)

        # Timestamp (Right Aligned)
        now_str = datetime.datetime.now().strftime("%a %H:%M")
        try:
            time_width = font_med.getlength(now_str)
        except AttributeError:
            time_width = font_med.getsize(now_str)[0]
        time_x = width - time_width - margin_x
        draw.text((time_x, int(height * 0.06)), now_str, fill=c_dim, font=font_med)

        # Current Price
        price_str = f"${current_price:,.2f}"
        price_y = int(height * 0.20)
        draw.text((margin_x, price_y), price_str, fill=c_text_main, font=font_giant)

        # Change %
        sign = "+" if is_bullish else ""
        change_str = f"{sign}{change_amt:.2f} ({sign}{change_pct:.2f}%)"
        change_y = int(height * 0.45)
        draw.text((margin_x, change_y), change_str, fill=c_accent, font=font_med)

        # -- DETAILS COLUMN (Right Side) --
        # Adjust layout based on width
        col_x_start = int(width * 0.625) # approx 500 for 800 width
        details_y_start = int(height * 0.18)
        details_y_end = int(height * 0.58)
        
        draw.line([(col_x_start, details_y_start), (col_x_start, details_y_end)], fill=c_grid, width=3)

        labels = [
            ("Open", f"${data['open']:.2f}"),
            ("High", f"${data['high']:.2f}"),
            ("Low", f"${data['low']:.2f}"),
            ("Vol", f"{data['volume'] / 1000000:.1f}M"),
        ]

        start_y = details_y_start
        label_x = col_x_start + int(width * 0.025)
        value_x = col_x_start + int(width * 0.175)
        row_height = int(height * 0.10)
        
        for label, value in labels:
            draw.text((label_x, start_y), label, fill=c_dim, font=font_med)
            draw.text((value_x, start_y), value, fill=c_text_main, font=font_med)
            start_y += row_height

        # -- DYNAMIC SPLIT CHART (Bottom Section) --
        chart_x_start = int(width * 0.03)
        chart_x_end = width - int(width * 0.03)
        chart_y_start = int(height * 0.625)
        chart_y_end = height - int(height * 0.08)

        history = data['history']

        if len(history) > 1:
            # Determine strict range including prev_close so the baseline is always visible/relevant
            min_p = min(min(history), prev_close)
            max_p = max(max(history), prev_close)

            # Min/Max Labels
            draw.text((chart_x_start, chart_y_start - int(height * 0.05)), f"High: {max_p:.2f}", fill=c_grid, font=font_small)
            draw.text((chart_x_start, chart_y_end + 5), f"Low: {min_p:.2f}", fill=c_grid, font=font_small)

            # Calculate the Y-coordinate for the "Zero Line" (Previous Close)
            y_base = self.map_range(prev_close, min_p, max_p, chart_y_end, chart_y_start)

            # Draw the dashed/solid baseline
            draw.line([(chart_x_start, y_base), (chart_x_end, y_base)], fill=c_grid, width=2)
            draw.text((chart_x_end - int(width * 0.075), y_base - 20), "Prev", fill=c_grid, font=font_tiny)

            # Pre-calculate all points
            points = []
            for i, price in enumerate(history):
                x = self.map_range(i, 0, len(history) - 1, chart_x_start, chart_x_end)
                y = self.map_range(price, min_p, max_p, chart_y_end, chart_y_start)
                points.append((x, y))

            # --- DRAW SEGMENTS WITH COLOR SPLIT ---
            line_width = max(2, int(width * 0.005))

            for i in range(len(points) - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]

                # Remember: Y grows downwards.
                # y < y_base means "Higher Price" (Green)
                # y > y_base means "Lower Price" (Red)

                if y1 <= y_base and y2 <= y_base:
                    # Entirely bullish segment
                    draw.line([(x1, y1), (x2, y2)], fill=c_up, width=line_width)

                elif y1 >= y_base and y2 >= y_base:
                    # Entirely bearish segment
                    draw.line([(x1, y1), (x2, y2)], fill=c_down, width=line_width)

                else:
                    # SPLIT CASE: The line crosses the baseline.
                    # We need to find the intersection point.
                    # Linear interpolation to find x where y = y_base

                    # Avoid division by zero
                    if y2 != y1:
                        ratio = (y_base - y1) / (y2 - y1)
                        x_cross = x1 + (x2 - x1) * ratio
                        y_cross = y_base
                    else:
                        x_cross = x1  # Should not happen in this else block
                        y_cross = y1

                    # Color logic for first half
                    color_1 = c_up if y1 < y_base else c_down
                    # Color logic for second half
                    color_2 = c_up if y2 < y_base else c_down

                    draw.line([(x1, y1), (x_cross, y_cross)], fill=color_1, width=line_width)
                    draw.line([(x_cross, y_cross), (x2, y2)], fill=color_2, width=line_width)

            # Sparkline dot at the end
            last_pt = points[-1]
            last_price = history[-1]

            # Dot color matches the end state
            dot_color = c_up if last_price >= prev_close else c_down

            r = max(4, int(width * 0.01))
            draw.ellipse((last_pt[0] - r, last_pt[1] - r, last_pt[0] + r, last_pt[1] + r), fill=dot_color)

        return image
