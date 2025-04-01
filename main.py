from machine import Pin, I2C, SPI
from pyb import Timer
from mfrc522 import MFRC522
import ssd1306
import time
import os
import random
import micropython
micropython.mem_info()

# 配置 SPI 接口
spi = SPI(2, baudrate=1000000, polarity=0, phase=0)

# 配置引脚
sda = Pin('PB12', Pin.OUT)  # NSS 引脚
rst = Pin('PA8', Pin.OUT)   # RST 引脚

# 初始化 RST 引脚
rst.value(1)

# 创建 RC522 对象 
rfid = MFRC522(spi, sda)

# 初始化 I2C，设置频率为 400 kHz
i2c = I2C(1, freq=400000)

# 初始化 OLED 显示屏
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# 初始化行和列的GPIO引脚，用于按钮矩阵
rows = [Pin('PA0', Pin.OUT), Pin('PA1', Pin.OUT), Pin('PA2', Pin.OUT), Pin('PA3', Pin.OUT)]
cols = [Pin('PB0', Pin.IN, Pin.PULL_UP), Pin('PB1', Pin.IN, Pin.PULL_UP),
        Pin('PA6', Pin.IN, Pin.PULL_UP), Pin('PB10', Pin.IN, Pin.PULL_UP)]

# 初始化 Timer 和 PWM，用于控制舵机
tim = Timer(4, freq=50)  # Timer 4, 50Hz
pwm_channel = tim.channel(4, Timer.PWM, pin=Pin('PB9'))

# 防止长按误触的阈值
DEBOUNCE_DELAY = 50  # ms
LONG_PRESS_DELAY = 500  # ms


def scan_keys():
    """
    扫描按钮矩阵的按键，并返回按键值
    """
    key_map = [
        ['1', '2', '3', 'A'],
        ['4', '5', '6', 'B'],
        ['7', '8', '9', 'C'],
        ['*', '0', '#', 'D']
    ]

    for row in range(4):
        rows[row].low()  # 将当前行拉低
        for col in range(4):
            if not cols[col].value():  # 检查当前列的值
                key = key_map[row][col]
                debounce_start = time.ticks_ms()
                while not cols[col].value():  # 等待按钮释放
                    if time.ticks_diff(time.ticks_ms(), debounce_start) > LONG_PRESS_DELAY:
                        rows[row].high()
                        return None
                    time.sleep_ms(DEBOUNCE_DELAY)
                rows[row].high()
                return key
        rows[row].high()  # 将当前行拉高
    return None


def set_servo_angle(angle):
    """
    设置舵机角度
    angle: 目标角度（0-180）
    """
    # 最小和最大脉冲宽度百分比对应0度和180度
    min_pulse = 3.0  # 0度对应的脉冲宽度百分比
    max_pulse = 10.5  # 180度对应的脉冲宽度百分比

    # 线性插值计算脉冲宽度百分比
    pulse_width_percent = min_pulse + (angle / 180.0) * (max_pulse - min_pulse)

    pwm_channel.pulse_width_percent(pulse_width_percent)
    time.sleep(1)  # 保持信号一段时间


def display(text):
    """
    在 OLED 显示屏上显示文本
    text: 要显示的文本
    """
    oled.fill(0)
    oled.text(text, 0, 0)
    oled.show()


def read_rfid():
    id = ''
    (stat, tag_type) = rfid.request(rfid.CARD_REQIDL)
    if stat == rfid.OK:
        (stat, uid) = rfid.anticoll()
        if stat == rfid.OK:
            rgb.colorful()
            for i in uid:
                id += str(i)
            time.sleep(0.2)
            rgb.off()
            return id
    return None


class Rgb:
    def __init__(self):
        # 配置 RGB LED 的引脚
        self.r = Pin('PB5', Pin.OUT)
        self.g = Pin('PB3', Pin.OUT)
        self.b = Pin('PA15', Pin.OUT)
        self.anode = Pin('PB4', Pin.OUT)
        self.anode.high()  # 使能 RGB LED 的正极

        # 使用 Timer 2 和 Timer 3 控制不同引脚的 PWM 输出
        self.timer2 = Timer(2, freq=1000)  # Timer 2，频率 1kHz
        self.timer3 = Timer(3, freq=1000)  # Timer 3，频率 1kHz

        # 配置 PWM 通道
        self.pwm_b = self.timer2.channel(1, Timer.PWM, pin=self.b, pulse_width_percent=100)  # 红色通道
        self.pwm_g = self.timer2.channel(2, Timer.PWM, pin=self.g, pulse_width_percent=100)  # 绿色通道
        self.pwm_r = self.timer3.channel(2, Timer.PWM, pin=self.r, pulse_width_percent=100)  # 蓝色通道

    def light(self, r_value, g_value, b_value):

        self.pwm_r.pulse_width_percent(100 - r_value)
        self.pwm_g.pulse_width_percent(100 - g_value)
        self.pwm_b.pulse_width_percent(100 - b_value)

    def off(self):

        self.pwm_r.pulse_width_percent(100)  # 红色通道占空比设为 100%，LED 关闭
        self.pwm_g.pulse_width_percent(100)  # 绿色通道占空比设为 100%，LED 关闭
        self.pwm_b.pulse_width_percent(100)  # 蓝色通道占空比设为 100%，LED 关闭
    
    def color_flash(self):
        self.light(255, 0, 0)
        time.sleep(0.2)
        self.light(0, 255, 0)
        time.sleep(0.2)
        self.light(0, 0, 255)
        time.sleep(0.2)
        self.light(0, 0, 0)

    def colorful(self):
        self.light(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


class Pw:
    def __init__(self, oled):
        """
        初始化密码类
        oled: OLED显示屏对象
        """
        # 预设密码
        self.password = self.load_password()  # 从文件中加载密码
        self.uid = self.load_uid()
        # 密码显示的X坐标
        self.x = [10, 30, 50, 70, 90, 110]
        # 密码显示的Y坐标
        self.y = 40
        # OLED对象
        self.oled = oled
        # 绘制分隔线
        self.content = ['Change password', 'Show password', 'Enter uid', 'View UID']
        self.old_line = [0, 9, len(self.content[0]) * 8]
        self.option = 0
        self.switch = 1

    def load_password(self):
        """
        从文件中加载密码
        """
        try:
            with open('password.txt', 'r') as f:
                password = f.read().split(',')
                if len(password) == 6:
                    return password
        except OSError:
            pass
        # 默认密码
        return ['1', '2', '3', '4', '5', '6']

    def save_password(self):
        """
        将密码保存到文件中
        """
        with open('password.txt', 'w') as f:
            f.write(','.join(self.password))

    def clear(self, x, y, l, w):
        """
        清除指定区域
        x: 区域的X坐标
        y: 区域的Y坐标
        l: 区域的宽度
        w: 区域的高度
        """
        for i in range(x, x + l):
            for j in range(y, y + w):
                self.oled.pixel(i, j, 0)
        self.oled.show()

    def draw_line(self):
        """
        绘制分隔线
        """
        for i, x in enumerate(self.x):
            self.oled.line(x, self.y + 10, x + 8, self.y + 10, 1)
        self.oled.show()

    def input_password(self, num):
        """
        输入密码
        num: 输入的密码列表
        """
        self.draw_line()
        digit = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
        ad = 0
        while ad < 6:

            n = scan_keys()
            if n == 'D' and 0 < ad:
                ad -= 1
                self.clear(self.x[ad], self.y, 8, 8)
                num.pop()

            elif n in digit:
                self.draw_password(n, ad)
                num.append(n)
                ad += 1

    def enter_password(self, num):
        self.oled.fill(0)
        self.oled.text('password', 0, 0)
        self.oled.show()
        self.input_password(num)

        while not self.jud(num):
            self.oled.fill(0)
            self.oled.text('try again', 0, 0)
            self.oled.show()
            rgb.color_flash()
            num.clear()
            self.input_password(num)


    def draw_password(self, n, ad):
        """
        绘制输入的密码
        n: 当前输入的数字
        ad: 当前数字的位置
        """
        self.oled.text(str(n), self.x[ad], self.y)
        if ad - 1 >= 0:
            self.clear(self.x[ad - 1], self.y, 8, 8)
            self.oled.text('*', self.x[ad - 1], self.y)
        self.oled.show()

    def menu_run(self):
        """
        根据选项执行相应操作
        """
        if self.option == 0:
            self.change_password()
        elif self.option == 1:
            self.show_password()
        elif self.option == 2:
            self.enter_uid()
        elif self.option == 3:
            self.view_uid()

        self.menu()

    def change_password(self):
        """
        更改密码
        """
        num = []
        self.oled.fill(0)
        self.oled.text('New Password', 0, 0)
        self.input_password(num)
        self.password = num
        self.save_password()  # 保存新密码
        for i in range(128, 49, -8):
            self.oled.fill(0)
            self,oled.text('OK', i, 30)
            self.oled.show()
        time.sleep(1)

    def show_password(self):
        """
        显示密码
        """
        self.oled.fill(0)
        self.oled.text('your password', 0, 0)
        self.draw_line()
        for i in range(6):
            self.oled.text(self.password[i], self.x[i], self.y)
        self.oled.show()
        while 1:
            if scan_keys() == 'D':
                return

    def jud(self, num, uid=None):
        """
        判断密码是否正确
        num: 输入的密码列表
        """
        if num == self.password:
            self.draw_pw_correct()
            return 1
        elif uid in self.uid:
            self.draw_pw_correct()
            return 1
        else:
            return 0

    def draw_pw_correct(self):
        """
        绘制密码正确的提示
        """
        for x in range(128, -1, -16):  # 从右向左移动
            self.oled.fill(0)
            self.oled.text('welcome', x, 0)
            self.oled.text('open', x + 25, 30)
            self.oled.show()
        rgb.light(0, 255, 0)
        set_servo_angle(90)
        self.hold_door()

    def control(self):
        """
        控制舵机和LED灯
        """
        if self.switch:
            rgb.light(0, 255, 0)
            set_servo_angle(90)
            self.switch = 0
        else:
            rgb.off()
            set_servo_angle(0)
            self.switch = 1

    def hold_door(self):
        """
        保持舵机打开状态一段时间，然后关闭
        """
        for i in range(10, -1, -1):
            self.clear(64, 30, 16, 8)
            self.oled.text(str(i), 64, 30)
            self.oled.show()
            time.sleep(1)

        self.clear(25, 30, 60, 8)
        self.oled.text('close', 25, 30)
        self.oled.show()
        rgb.off()
        set_servo_angle(0)

    def draw_cursor(self, v):
        """
        绘制光标
        v: 光标移动方向
        """
        if v == 0:
            self.oled.line(self.old_line[0], self.old_line[1], self.old_line[2], self.old_line[1], 1)
            self.oled.show()
        else:
            if 0 <= self.option + v < len(self.content):
                self.option += v
                new_line = [0, self.option * 15 + 9, len(self.content[self.option]) * 8]
                self.clear(self.old_line[0], self.old_line[1], self.old_line[2] + 1, 1)
                self.oled.line(new_line[0], new_line[1], new_line[2], new_line[1], 1)
                self.oled.show()
                self.old_line = new_line

    def menu(self):
        """
        显示密码菜单
        """
        self.oled.fill(0)
        for i in range(len(self.content)):
            self.oled.text(self.content[i], 0, 15 * i)
        self.oled.show()
        self.draw_cursor(0)

    def load_uid(self):
        """
        从文件中加载密码
        """
        try:
            with open('uid.txt', 'r') as f:
                uid = f.read().split(',')
                return uid
        except OSError:
            pass
        # 默认密码
        return []

    def enter_uid(self):
        rst.value(1)
        self.oled.fill(0)
        self.oled.text('uid', 0, 0)
        self.oled.show()
        while 1:
            uid = read_rfid()
            if uid:
                break
        if uid not in self.uid:
            self.uid.append(uid)
            self.oled.text(uid, 0, 32)
            self.oled.show()
            with open('uid.txt', 'w') as f:
                f.write(','.join(self.uid))
            time.sleep(3)
        else:
            self.oled.fill(0)
            self.oled.text('The card ', 0, 0)
            self.oled.text('already exists', 16, 10)
            self.oled.show()
            time.sleep(3)

    def view_uid(self):
        try:
            y = 15
            old_line = [0, 24, len(self.uid[0]) * 8]
            option = 0
            self.oled.fill(0)
            self.oled.text('Your Uid', 0, 0)
            for i in self.uid:
                self.oled.text(i, 0, y)
                y += 15
            self.oled.line(old_line[0], old_line[1], old_line[2], old_line[1], 1)
            self.oled.show()
            while 1:
                key = scan_keys()
                if key == 'B':
                    self.oled.fill(0)
                    self.oled.text('Delete this UID', 0, 0)
                    self.oled.text('Are you sure?', 0, 20)
                    self.oled.show()
                    while 1:
                        key = scan_keys()
                        if key == 'B':
                            del self.uid[option]
                            os.remove('uid.txt')
                            with open('uid.txt', 'w', encoding='utf-8') as f:
                                f.write(','.join(self.uid))
                            option = 0
                            self.oled.fill(0)
                            y = 15
                            self.oled.text('Your Uid', 0, 0)
                            for i in self.uid:
                                self.oled.text(i, 0, y)
                                y += 15
                            old_line = [0, 24, len(self.uid[0]) * 8]
                            self.oled.line(old_line[0], old_line[1], old_line[2], old_line[1], 1)
                            self.oled.show()
                            break
                        elif key == 'D':
                            self.view_uid()
                            return

                elif key == 'D':
                    return
                elif key == 'A' or key == 'C':
                    if key == 'A' and 0 <= option - 1 < len(self.uid):
                        option -= 1
                    elif key == 'C' and 0 <= option + 1 < len(self.uid):
                        option += 1
                    new_line = [0, option * 15 + 24, len(self.uid[option]) * 8]
                    self.clear(old_line[0], old_line[1], old_line[2] + 1, 1)
                    self.oled.line(new_line[0], new_line[1], new_line[2], new_line[1], 1)
                    self.oled.show()
                    old_line = new_line

        except:
            self.oled.fill(0)
            self.oled.text("No UID", 0, 0)
            self.oled.text('Please enter', 0, 20)
            self.oled.show()
            time.sleep(3)
            return


def main():
    global rgb
    """
    主函数，程序入口
    """
    set_servo_angle(0)
    oled.fill(0)
    oled.text('Smart Home', 0, 20)
    oled.text('Defense System', 16, 30)
    oled.show()

    rgb = Rgb()

    # 创建密码对象
    p = Pw(oled)
    num = []
    uid = None

    while not p.jud(num, uid):
        uid = read_rfid()
        if scan_keys() == 'B':
            p.enter_password(num)
            break

    while True:
        key = scan_keys()
        if key == 'B':
            p.menu()
            break
        elif key == '#':
            if p.switch:
                p.clear(25, 30, 60, 8)
                oled.text('open', 25, 30)
            else:
                p.clear(25, 30, 60, 8)
                oled.text('close', 25, 30)
            oled.show()
            p.control()

    while True:
        key = scan_keys()
        if key == 'A':
            p.draw_cursor(-1)
        elif key == 'C':
            p.draw_cursor(1)
        elif key == 'B':
            p.menu_run()
        elif key == '#':
            p.control()


if __name__ == '__main__':

    main()
