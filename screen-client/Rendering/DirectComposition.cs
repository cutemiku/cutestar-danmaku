using System.Runtime.InteropServices;

namespace Cutestar.Screen.Rendering;

/// <summary>
/// DirectComposition COM 互操作。
/// dcomp.dll 的 IDCompositionDevice / IDCompositionTarget / IDCompositionVisual。
/// 用 ComImport 完整声明，让 CLR 生成正确的 vtable 布局。
/// </summary>
internal static unsafe class DirectComposition
{
    [DllImport("dcomp.dll")]
    private static extern int DCompositionCreateDevice(
        IntPtr d3dDevice, in Guid iid, out IntPtr devicePtr);

    private static readonly Guid IID_IDCompositionDevice =
        new("C37EA93A-E7AA-450D-B16F-9746CB0407F3");

    public static IDCompositionDevice? CreateDevice(IntPtr d3dDevicePtr)
    {
        int hr = DCompositionCreateDevice(d3dDevicePtr, in IID_IDCompositionDevice, out var devicePtr);
        if (hr != 0 || devicePtr == IntPtr.Zero) return null;
        return (IDCompositionDevice)Marshal.GetObjectForIUnknown(devicePtr);
    }
}

[ComImport]
[Guid("C37EA93A-E7AA-450D-B16F-9746CB0407F3")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDCompositionDevice
{
    [PreserveSig]
    int CreateTargetForHwnd(IntPtr hwnd, [MarshalAs(UnmanagedType.Bool)] bool topmost, out IDCompositionTarget target);
    [PreserveSig]
    int CreateVisual(out IDCompositionVisual visual);
    [PreserveSig]
    int CreateSurface(int width, int height, int pixelFormat, int alphaMode, out IntPtr surface);
    [PreserveSig]
    int CreateVirtualSurface(int initialWidth, int initialHeight, int pixelFormat, int alphaMode, out IntPtr virtualSurface);
    [PreserveSig]
    int CreateTranslateTransform(out IntPtr translateTransform);
    [PreserveSig]
    int CreateScaleTransform(out IntPtr scaleTransform);
    [PreserveSig]
    int CreateRotateTransform(out IntPtr rotateTransform);
    [PreserveSig]
    int CreateSkewTransform(out IntPtr skewTransform);
    [PreserveSig]
    int CreateMatrixTransform(out IntPtr matrixTransform);
    [PreserveSig]
    int CreateTransformGroup(IntPtr transforms, int elements, out IntPtr transformGroup);
    [PreserveSig]
    int CreateTranslateTransform3D(out IntPtr translateTransform3D);
    [PreserveSig]
    int CreateScaleTransform3D(out IntPtr scaleTransform3D);
    [PreserveSig]
    int CreateRotateTransform3D(out IntPtr rotateTransform3D);
    [PreserveSig]
    int CreateMatrixTransform3D(out IntPtr matrixTransform3D);
    [PreserveSig]
    int CreateTransform3DGroup(IntPtr transforms3D, int elements, out IntPtr transform3DGroup);
    [PreserveSig]
    int CreateEffectGroup(out IntPtr effectGroup);
    [PreserveSig]
    int CreateRectangleClip(out IntPtr clip);
    [PreserveSig]
    int CreateGaussianBlurEffect(out IntPtr effect);
    [PreserveSig]
    int CreateTableTransferEffect(out IntPtr effect);
    [PreserveSig]
    int CreateCompositeEffect(out IntPtr effect);
    [PreserveSig]
    int CreateOpacityEffect(out IntPtr effect);
    [PreserveSig]
    int Create3DTransformEffect(out IntPtr effect);
    [PreserveSig]
    int CreateTurbulenceEffect(out IntPtr effect);
    [PreserveSig]
    int CreateShadowEffect(out IntPtr effect);
    [PreserveSig]
    int CreateHueRotateEffect(out IntPtr effect);
    [PreserveSig]
    int CreateSaturateEffect(out IntPtr effect);
    [PreserveSig]
    int CreateBrightnessEffect(out IntPtr effect);
    [PreserveSig]
    int CreateArithmeticCompositeEffect(out IntPtr effect);
    [PreserveSig]
    int CreateLinearTransferEffect(out IntPtr effect);
    [PreserveSig]
    int CreateAnimation(out IntPtr animation);
    [PreserveSig]
    int CreateSurfaceFromHandle(IntPtr handle, out IntPtr surface);
    [PreserveSig]
    int CreateSurfaceFromSharedHandle(IntPtr handle, out IntPtr surface);
    [PreserveSig]
    int Commit();
    [PreserveSig]
    int WaitForCommitCompletion();
    [PreserveSig]
    int GetFrameStatistics(out IntPtr statistics);
}

[ComImport]
[Guid("EACDD04C-117E-4E17-88F4-D1B12B0E3D89")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDCompositionTarget
{
    [PreserveSig]
    int SetRoot(IDCompositionVisual visual);
}

[ComImport]
[Guid("4D93059D-097B-4651-9A60-F0F25116E2F3")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IDCompositionVisual
{
    [PreserveSig]
    int AddVisual(IDCompositionVisual visual, [MarshalAs(UnmanagedType.Bool)] bool insertAbove, IDCompositionVisual referenceVisual);
    [PreserveSig]
    int RemoveVisual(IDCompositionVisual visual);
    [PreserveSig]
    int RemoveAllVisuals();
    [PreserveSig]
    int SetOffsetX(float offsetX);
    [PreserveSig]
    int SetOffsetY(float offsetY);
    [PreserveSig]
    int SetTransform(IntPtr transform);
    [PreserveSig]
    int SetTransformParent(IDCompositionVisual visual);
    [PreserveSig]
    int SetEffect(IntPtr effect);
    [PreserveSig]
    int SetOverlayMode(int mode);
    [PreserveSig]
    int SetClip(IntPtr clip);
    [PreserveSig]
    int SetContent(IntPtr content);
}
