// P0 live probe, raw il2cpp route.
//
// The generated interop assemblies resolve methods by *token* (GetIl2CppMethodByToken).
// Their tokens come from an unstripped blank player, the shipped game is stripped, so every
// call through an interop proxy lands on a wrong or null MethodInfo and access-violates.
// Class pointers are resolved by name and are fine; only method resolution is broken.
//
// Everything below therefore goes through the exported il2cpp_* API and resolves by name.
// Interop types are still used for one thing only: ClassInjector needs a managed MonoBehaviour
// subclass to inject, and injection is name/pointer based, not token based.
#nullable enable

using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using BepInEx.Unity.IL2CPP.Hook;
using Il2CppInterop.Runtime;
using Il2CppInterop.Runtime.Injection;
using UnityEngine;

namespace Gakumas.AvatarRuntime.BepInEx;

internal static class Il2
{
    private const string Lib = "GameAssembly";

    [DllImport(Lib)] internal static extern IntPtr il2cpp_domain_get();
    [DllImport(Lib, CharSet = CharSet.Ansi)] internal static extern IntPtr il2cpp_domain_assembly_open(IntPtr domain, string name);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_assembly_get_image(IntPtr assembly);
    [DllImport(Lib, CharSet = CharSet.Ansi)] internal static extern IntPtr il2cpp_class_from_name(IntPtr image, string ns, string name);
    [DllImport(Lib, CharSet = CharSet.Ansi)] internal static extern IntPtr il2cpp_class_get_method_from_name(IntPtr klass, string name, int argsCount);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_class_get_methods(IntPtr klass, ref IntPtr iterator);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_method_get_name(IntPtr method);
    [DllImport(Lib)] internal static extern uint il2cpp_method_get_param_count(IntPtr method);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_method_get_param(IntPtr method, uint index);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_method_get_return_type(IntPtr method);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_type_get_name(IntPtr type);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_object_get_class(IntPtr obj);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_class_get_parent(IntPtr klass);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_class_get_fields(IntPtr klass, ref IntPtr iterator);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_field_get_name(IntPtr field);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_field_get_type(IntPtr field);
    [DllImport(Lib, CharSet = CharSet.Ansi)] internal static extern IntPtr il2cpp_class_get_field_from_name(IntPtr klass, string name);
    [DllImport(Lib)] internal static extern int il2cpp_field_get_flags(IntPtr field);
    [DllImport(Lib)] internal static extern void il2cpp_field_get_value(IntPtr obj, IntPtr field, IntPtr value);
    [DllImport(Lib)] internal static extern void il2cpp_field_set_value(IntPtr obj, IntPtr field, IntPtr value);

    internal static void SetFloat(IntPtr instance, IntPtr field, float value)
    {
        Marshal.WriteInt32(ValueBuffer, BitConverter.SingleToInt32Bits(value));
        il2cpp_field_set_value(instance, field, ValueBuffer);
    }
    [DllImport(Lib)] internal static extern IntPtr il2cpp_class_from_il2cpp_type(IntPtr type);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_class_get_element_class(IntPtr klass);
    [DllImport(Lib)] [return: MarshalAs(UnmanagedType.I1)] internal static extern bool il2cpp_class_is_valuetype(IntPtr klass);
    [DllImport(Lib)] [return: MarshalAs(UnmanagedType.I1)] internal static extern bool il2cpp_class_is_enum(IntPtr klass);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_runtime_invoke(IntPtr method, IntPtr obj, IntPtr args, out IntPtr exception);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_object_new(IntPtr klass);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_class_get_type(IntPtr klass);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_type_get_object(IntPtr type);
    [DllImport(Lib, CharSet = CharSet.Ansi)] internal static extern IntPtr il2cpp_string_new(string value);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_string_chars(IntPtr str);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_domain_get_assemblies(IntPtr domain, out uint size);
    [DllImport(Lib)] internal static extern IntPtr il2cpp_array_new(IntPtr elementClass, ulong length);

    // The game's own code is not necessarily in Assembly-CSharp, and guessing the image wastes a
    // launch. Scan every loaded assembly instead.
    internal static IntPtr FindClass(string ns, string name)
    {
        var assemblies = il2cpp_domain_get_assemblies(il2cpp_domain_get(), out var count);
        for (var index = 0u; index < count; index++)
        {
            var assembly = Marshal.ReadIntPtr(assemblies, (int)index * IntPtr.Size);
            var image = assembly == IntPtr.Zero ? IntPtr.Zero : il2cpp_assembly_get_image(assembly);
            if (image == IntPtr.Zero)
                continue;
            var klass = il2cpp_class_from_name(image, ns, name);
            if (klass != IntPtr.Zero)
                return klass;
        }
        throw new InvalidOperationException($"il2cpp: class {ns}.{name} not found in any assembly");
    }

    // MethodInfo's first field is the native code pointer — that is what a detour replaces.
    internal static IntPtr CodePointer(IntPtr methodInfo) =>
        methodInfo == IntPtr.Zero ? IntPtr.Zero : Marshal.ReadIntPtr(methodInfo);

    internal static string Describe(IntPtr instance, Func<IntPtr, string> unityName)
    {
        if (instance == IntPtr.Zero)
            return "null";
        var klass = il2cpp_object_get_class(instance);
        var name = ClassName(klass);
        return RenderCollection(instance, name, string.Empty, unityName)
               ?? $"<{name}>{(IsUnityObject(klass) ? $" \"{unityName(instance)}\"" : string.Empty)}";
    }

    private static IntPtr Require(IntPtr pointer, string what) =>
        pointer != IntPtr.Zero ? pointer : throw new InvalidOperationException($"il2cpp: {what} not resolved");

    internal static IntPtr Image(string assemblyName) =>
        Require(il2cpp_assembly_get_image(Require(il2cpp_domain_assembly_open(il2cpp_domain_get(), assemblyName), $"assembly {assemblyName}")), $"image {assemblyName}");

    internal static IntPtr Class(IntPtr image, string ns, string name) =>
        Require(il2cpp_class_from_name(image, ns, name), $"class {ns}.{name}");

    internal static IntPtr Method(IntPtr klass, string name, int argsCount) =>
        Require(il2cpp_class_get_method_from_name(klass, name, argsCount), $"method {name}/{argsCount}");

    // Name + argument count is ambiguous whenever a class has same-arity overloads
    // (GetComponentsInChildren has both (Type,bool) and (bool,List<T>)), and picking the wrong
    // one fails silently. Match the parameter type names instead.
    internal static IntPtr MethodExact(IntPtr klass, string name, params string[] parameterTypes)
    {
        // il2cpp_class_get_methods lists declared methods only, so an inherited target (BuildModel
        // lives on the VL base) is invisible unless the parent chain is walked.
        for (var current = klass; current != IntPtr.Zero; current = il2cpp_class_get_parent(current))
        {
            var iterator = IntPtr.Zero;
            IntPtr method;
            while ((method = il2cpp_class_get_methods(current, ref iterator)) != IntPtr.Zero)
            {
                if (Marshal.PtrToStringAnsi(il2cpp_method_get_name(method)) != name)
                    continue;
                if (il2cpp_method_get_param_count(method) != parameterTypes.Length)
                    continue;
                var matched = true;
                for (var index = 0u; index < parameterTypes.Length; index++)
                {
                    if (Marshal.PtrToStringAnsi(il2cpp_type_get_name(il2cpp_method_get_param(method, index))) == parameterTypes[index])
                        continue;
                    matched = false;
                    break;
                }
                if (matched)
                    return method;
            }
        }
        throw new InvalidOperationException($"il2cpp: method {name}({string.Join(", ", parameterTypes)}) not resolved");
    }

    internal static IntPtr TypeObject(IntPtr klass) => il2cpp_type_get_object(il2cpp_class_get_type(klass));

    internal static string Ansi(IntPtr nativeString) => Marshal.PtrToStringAnsi(nativeString) ?? string.Empty;
    internal static string TypeName(IntPtr type) => type == IntPtr.Zero ? "?" : Ansi(il2cpp_type_get_name(type));
    internal static string ClassName(IntPtr klass) => klass == IntPtr.Zero ? "?" : TypeName(il2cpp_class_get_type(klass));

    // Foreign to us, but not interesting to dump: the framework types around the game's own code.
    internal static bool IsForeign(string typeName) =>
        typeName.StartsWith("System.", StringComparison.Ordinal) ||
        typeName.StartsWith("UnityEngine.", StringComparison.Ordinal) ||
        typeName.StartsWith("Unity.", StringComparison.Ordinal) ||
        typeName.StartsWith("Cysharp.", StringComparison.Ordinal) ||
        typeName.StartsWith("Il2Cpp", StringComparison.Ordinal) ||
        typeName == "?";

    private static IntPtr ClassOf(IntPtr type)
    {
        if (type == IntPtr.Zero)
            return IntPtr.Zero;
        var klass = il2cpp_class_from_il2cpp_type(type);
        // T[] carries no members of its own; the element type is what we want to follow.
        var element = klass == IntPtr.Zero ? IntPtr.Zero : il2cpp_class_get_element_class(klass);
        return element != IntPtr.Zero && element != klass ? element : klass;
    }

    // Live reflection over the target: the shipped GameAssembly answers "what is actually on this
    // object" better than any offline dump, and it is immune to stripping and token drift.
    // `referenced` collects the classes this one mentions, so the caller can walk outward.
    internal static string DumpClass(IntPtr klass, List<IntPtr>? referenced = null)
    {
        var text = new System.Text.StringBuilder();
        for (var current = klass; current != IntPtr.Zero; current = il2cpp_class_get_parent(current))
        {
            var name = ClassName(current);
            text.AppendLine($"== {name}");
            if (IsForeign(name))
                break;

            var fieldIterator = IntPtr.Zero;
            IntPtr field;
            while ((field = il2cpp_class_get_fields(current, ref fieldIterator)) != IntPtr.Zero)
            {
                var fieldType = il2cpp_field_get_type(field);
                text.AppendLine($"   field {TypeName(fieldType)} {Ansi(il2cpp_field_get_name(field))}");
                referenced?.Add(ClassOf(fieldType));
            }

            var methodIterator = IntPtr.Zero;
            IntPtr method;
            while ((method = il2cpp_class_get_methods(current, ref methodIterator)) != IntPtr.Zero)
            {
                var parameters = new List<string>();
                var count = il2cpp_method_get_param_count(method);
                for (var index = 0u; index < count; index++)
                {
                    var parameterType = il2cpp_method_get_param(method, index);
                    parameters.Add(TypeName(parameterType));
                    referenced?.Add(ClassOf(parameterType));
                }
                var returnType = il2cpp_method_get_return_type(method);
                referenced?.Add(ClassOf(returnType));
                text.AppendLine($"   {TypeName(returnType)} {Ansi(il2cpp_method_get_name(method))}({string.Join(", ", parameters)})");
            }
        }
        return text.ToString();
    }

    private const int FieldStaticOrLiteral = 0x10 | 0x40;
    private static readonly IntPtr ValueBuffer = Marshal.AllocHGlobal(64);

    // il2cpp_field_get_value copies the field's *full* size into the buffer, so a struct field
    // larger than the buffer corrupts the heap and the process dies somewhere unrelated later.
    // Only these are read; every other value type is reported by name and never copied.
    private static readonly HashSet<string> ReadableValueTypes = new()
    {
        "System.Boolean", "System.Byte", "System.SByte", "System.Char",
        "System.Int16", "System.UInt16", "System.Int32", "System.UInt32",
        "System.Int64", "System.UInt64", "System.Single", "System.Double",
        "System.IntPtr", "System.UIntPtr",
        "UnityEngine.Vector2", "UnityEngine.Vector3", "UnityEngine.Vector4",
        "UnityEngine.Quaternion", "UnityEngine.Color",
    };

    internal static bool IsUnityObject(IntPtr klass)
    {
        for (var current = klass; current != IntPtr.Zero; current = il2cpp_class_get_parent(current))
            if (ClassName(current) == "UnityEngine.Object")
                return true;
        return false;
    }

    // Live field values off a real instance. Reference fields are reported as their *runtime*
    // class, which is the whole point: the declared type is often an interface or a base.
    internal static void DumpInstance(IntPtr instance, int depth, System.Text.StringBuilder text, string indent, Func<IntPtr, string> unityName)
    {
        if (instance == IntPtr.Zero)
            return;
        for (var current = il2cpp_object_get_class(instance); current != IntPtr.Zero; current = il2cpp_class_get_parent(current))
        {
            if (IsForeign(ClassName(current)))
                break;
            var iterator = IntPtr.Zero;
            IntPtr field;
            while ((field = il2cpp_class_get_fields(current, ref iterator)) != IntPtr.Zero)
            {
                if ((il2cpp_field_get_flags(field) & FieldStaticOrLiteral) != 0)
                    continue;
                var fieldType = il2cpp_field_get_type(field);
                var typeName = TypeName(fieldType);
                var fieldName = Ansi(il2cpp_field_get_name(field));
                var declared = il2cpp_class_from_il2cpp_type(fieldType);
                var isValueType = declared != IntPtr.Zero && il2cpp_class_is_valuetype(declared);
                if (isValueType && !ReadableValueTypes.Contains(typeName) && !il2cpp_class_is_enum(declared))
                {
                    text.AppendLine($"{indent}{typeName} {fieldName} = <struct>");
                    continue;
                }
                il2cpp_field_get_value(instance, field, ValueBuffer);
                text.AppendLine($"{indent}{typeName} {fieldName} = {RenderValue(declared, isValueType, typeName, depth, indent, unityName)}");
            }
        }
    }

    private static string RenderValue(IntPtr declaredClass, bool isValueType, string typeName, int depth, string indent, Func<IntPtr, string> unityName)
    {
        switch (typeName)
        {
            case "System.Boolean": return (Marshal.ReadByte(ValueBuffer) != 0).ToString();
            case "System.Byte": return Marshal.ReadByte(ValueBuffer).ToString();
            case "System.Int32": case "System.UInt32": return Marshal.ReadInt32(ValueBuffer).ToString();
            case "System.Int64": case "System.UInt64": return Marshal.ReadInt64(ValueBuffer).ToString();
            case "System.Single": return BitConverter.Int32BitsToSingle(Marshal.ReadInt32(ValueBuffer)).ToString("R");
            case "System.Double": return BitConverter.Int64BitsToDouble(Marshal.ReadInt64(ValueBuffer)).ToString("R");
            case "UnityEngine.Vector3": return $"({ReadFloat(0)}, {ReadFloat(4)}, {ReadFloat(8)})";
            case "UnityEngine.Quaternion": case "UnityEngine.Color":
                return $"({ReadFloat(0)}, {ReadFloat(4)}, {ReadFloat(8)}, {ReadFloat(12)})";
            case "System.String": return $"\"{Str(Marshal.ReadIntPtr(ValueBuffer))}\"";
        }

        // Value types sit inline in the buffer — reading one as a pointer dereferences garbage.
        if (isValueType)
            return il2cpp_class_is_enum(declaredClass)
                ? Marshal.ReadInt32(ValueBuffer).ToString()
                : $"0x{Marshal.ReadInt64(ValueBuffer):X16}";

        var pointer = Marshal.ReadIntPtr(ValueBuffer);
        if (pointer == IntPtr.Zero)
            return "null";

        var runtimeClass = il2cpp_object_get_class(pointer);
        var runtimeName = ClassName(runtimeClass);
        var suffix = IsUnityObject(runtimeClass) ? $" \"{unityName(pointer)}\"" : string.Empty;

        var collection = RenderCollection(pointer, runtimeName, indent, unityName);
        if (collection != null)
            return collection;

        if (depth <= 0 || IsForeign(runtimeName))
            return $"<{runtimeName}>{suffix}";

        var nested = new System.Text.StringBuilder();
        nested.AppendLine($"<{runtimeName}>{suffix}");
        DumpInstance(pointer, depth - 1, nested, indent + "    ", unityName);
        return nested.ToString().TrimEnd();
    }

    private static float ReadFloat(int offset) => BitConverter.Int32BitsToSingle(Marshal.ReadInt32(ValueBuffer, offset));

    private const int MaxCollectionItems = 40;

    // The interesting content lives in List<T> and T[] fields — asset names, parts, bone chains.
    // Returns null when the object is not a collection, so the caller falls through.
    internal static string? RenderCollection(IntPtr instance, string runtimeName, string indent, Func<IntPtr, string> unityName)
    {
        var array = IntPtr.Zero;
        var count = 0;
        if (runtimeName.EndsWith("[]", StringComparison.Ordinal))
        {
            array = instance;
            count = Length(array);
        }
        // il2cpp_type_get_name renders generics as List<T>, never as List`1 — matching the
        // backtick form silently disabled this whole branch.
        else if (runtimeName.StartsWith("System.Collections.Generic.List<", StringComparison.Ordinal))
        {
            var klass = il2cpp_object_get_class(instance);
            var items = il2cpp_class_get_field_from_name(klass, "_items");
            var size = il2cpp_class_get_field_from_name(klass, "_size");
            if (items == IntPtr.Zero || size == IntPtr.Zero)
                return null;
            il2cpp_field_get_value(instance, items, ValueBuffer);
            array = Marshal.ReadIntPtr(ValueBuffer);
            il2cpp_field_get_value(instance, size, ValueBuffer);
            count = Marshal.ReadInt32(ValueBuffer);
        }
        else
        {
            return null;
        }

        if (array == IntPtr.Zero || count <= 0)
            return $"<{runtimeName}> (0)";

        // Value-type elements sit inline in the array; reading them as pointers is not safe.
        var elementClass = il2cpp_class_get_element_class(il2cpp_object_get_class(array));
        if (elementClass != IntPtr.Zero && il2cpp_class_is_valuetype(elementClass))
            return $"<{runtimeName}> ({count} x {ClassName(elementClass)} struct)";

        var text = new System.Text.StringBuilder();
        text.AppendLine($"<{runtimeName}> ({count})");
        for (var index = 0; index < Math.Min(count, MaxCollectionItems); index++)
        {
            var item = Item(array, index);
            if (item == IntPtr.Zero)
            {
                text.AppendLine($"{indent}    [{index}] null");
                continue;
            }
            var itemClass = il2cpp_object_get_class(item);
            var itemName = ClassName(itemClass);
            var rendered = itemName == "System.String"
                ? $"\"{Str(item)}\""
                : $"<{itemName}>{(IsUnityObject(itemClass) ? $" \"{unityName(item)}\"" : string.Empty)}";
            text.AppendLine($"{indent}    [{index}] {rendered}");
        }
        if (count > MaxCollectionItems)
            text.AppendLine($"{indent}    ... {count - MaxCollectionItems} more");
        return text.ToString().TrimEnd();
    }

    // ponytail: single scratch buffer per primitive kind — every call site runs on the Unity
    // main thread, one invoke at a time. Add a stack of buffers only if that stops being true.
    private static readonly IntPtr Int32Arg = Marshal.AllocHGlobal(4);
    private static readonly IntPtr BoolArg = Marshal.AllocHGlobal(1);

    internal static IntPtr Arg(int value) { Marshal.WriteInt32(Int32Arg, value); return Int32Arg; }
    internal static IntPtr Arg(bool value) { Marshal.WriteByte(BoolArg, (byte)(value ? 1 : 0)); return BoolArg; }

    // Never hand a null MethodInfo to runtime_invoke — that is exactly the access violation
    // the interop route dies on, and it is unrecoverable. Fail loudly instead.
    internal static IntPtr Invoke(IntPtr method, IntPtr instance, params IntPtr[] args)
    {
        Require(method, "method");
        IntPtr result;
        IntPtr exception;
        if (args.Length == 0)
        {
            result = il2cpp_runtime_invoke(method, instance, IntPtr.Zero, out exception);
        }
        else
        {
            var pinned = GCHandle.Alloc(args, GCHandleType.Pinned);
            try { result = il2cpp_runtime_invoke(method, instance, pinned.AddrOfPinnedObject(), out exception); }
            finally { pinned.Free(); }
        }
        if (exception != IntPtr.Zero)
            throw new InvalidOperationException("il2cpp: managed exception thrown by invoked method");
        return result;
    }

    internal static string Str(IntPtr il2CppString)
    {
        if (il2CppString == IntPtr.Zero)
            return string.Empty;
        var chars = il2cpp_string_chars(il2CppString);
        return chars == IntPtr.Zero ? string.Empty : Marshal.PtrToStringUni(chars) ?? string.Empty;
    }

    // Value types come back boxed; the payload starts right after the object header.
    private const int BoxPayload = 0x10;

    internal static int Int(IntPtr boxed) => boxed == IntPtr.Zero ? 0 : Marshal.ReadInt32(boxed, BoxPayload);
    internal static bool Bool(IntPtr boxed) => boxed != IntPtr.Zero && Marshal.ReadByte(boxed, BoxPayload) != 0;
    internal static float Float(IntPtr boxed) => boxed == IntPtr.Zero ? 0f : BitConverter.Int32BitsToSingle(Marshal.ReadInt32(boxed, BoxPayload));

    /// <summary>A float inside a boxed struct — Color's four channels sit at 0/4/8/12.</summary>
    internal static float FloatAt(IntPtr boxed, int offset) =>
        boxed == IntPtr.Zero ? 0f : BitConverter.Int32BitsToSingle(Marshal.ReadInt32(boxed, BoxPayload + offset));
    internal static float[] Floats(IntPtr boxed, int count)
    {
        var values = new float[count];
        if (boxed == IntPtr.Zero)
            return values;
        for (var index = 0; index < count; index++)
            values[index] = BitConverter.Int32BitsToSingle(Marshal.ReadInt32(boxed, BoxPayload + index * 4));
        return values;
    }

    // Il2CppArray on x64: object header 0x10, bounds 0x08, max_length 0x08, then the elements.
    internal static int Length(IntPtr array) => array == IntPtr.Zero ? 0 : (int)Marshal.ReadInt64(array, 0x18);
    internal static IntPtr Item(IntPtr array, int index) => Marshal.ReadIntPtr(array, 0x20 + index * IntPtr.Size);
    // il2cpp uses Boehm GC, so a reference slot can be overwritten without a write barrier.
    internal static void SetItem(IntPtr array, int index, IntPtr value) => Marshal.WriteIntPtr(array, 0x20 + index * IntPtr.Size, value);
}

// Resolved once per process. Everything here is name based, so it survives stripping and
// token drift; anything the target genuinely lacks throws at resolution time with its name.
internal sealed class UnityApi
{
    internal readonly IntPtr ObjectGetName, ComponentGetGameObject, ComponentGetTransform, ComponentGetComponentsInChildren;
    internal readonly IntPtr BehaviourGetEnabled, GameObjectGetScene, GameObjectGetActiveInHierarchy;
    internal readonly IntPtr TransformGetParent, TransformGetChildCount, TransformGetChild;
    internal readonly IntPtr TransformLocalPosition, TransformLocalRotation, TransformLocalScale;
    internal readonly IntPtr AnimatorClass, AnimatorIsHuman, AnimatorIsInitialized, AnimatorGetAvatar, AnimatorGetBoneTransform;
    internal readonly IntPtr AnimatorApplyRootMotion, AnimatorUpdateMode, AnimatorCullingMode, AnimatorController;
    internal readonly IntPtr AvatarIsValid, AvatarIsHuman;
    internal readonly IntPtr SkinnedClass, SkinnedSharedMesh, SkinnedBones, SkinnedRootBone, SkinnedBlendShapeWeight;
    internal readonly IntPtr RendererGetEnabled, RendererSharedMaterials, MaterialGetShader;
    internal readonly IntPtr MeshBlendShapeCount, MeshGetBlendShapeName, MeshVertexCount, MeshSubMeshCount;
    internal readonly IntPtr ResourcesFindObjectsOfTypeAll, TransformTypeObject, SkinnedTypeObject, AnimatorTypeObject;
    internal readonly IntPtr GameObjectGetComponents, ComponentTypeObject, RendererTypeObject;
    internal readonly IntPtr SwingBoneTypeObject;

    internal UnityApi()
    {
        var core = Il2.Image("UnityEngine.CoreModule");
        var animation = Il2.Image("UnityEngine.AnimationModule");

        var objectClass = Il2.Class(core, "UnityEngine", "Object");
        var componentClass = Il2.Class(core, "UnityEngine", "Component");
        var behaviourClass = Il2.Class(core, "UnityEngine", "Behaviour");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var transformClass = Il2.Class(core, "UnityEngine", "Transform");
        var rendererClass = Il2.Class(core, "UnityEngine", "Renderer");
        var materialClass = Il2.Class(core, "UnityEngine", "Material");
        var meshClass = Il2.Class(core, "UnityEngine", "Mesh");
        var resourcesClass = Il2.Class(core, "UnityEngine", "Resources");
        var avatarClass = Il2.Class(animation, "UnityEngine", "Avatar");
        SkinnedClass = Il2.Class(core, "UnityEngine", "SkinnedMeshRenderer");
        AnimatorClass = Il2.Class(animation, "UnityEngine", "Animator");

        ObjectGetName = Il2.Method(objectClass, "get_name", 0);
        ComponentGetGameObject = Il2.Method(componentClass, "get_gameObject", 0);
        ComponentGetTransform = Il2.Method(componentClass, "get_transform", 0);
        ComponentGetComponentsInChildren = Il2.MethodExact(componentClass, "GetComponentsInChildren", "System.Type", "System.Boolean");
        BehaviourGetEnabled = Il2.Method(behaviourClass, "get_enabled", 0);
        GameObjectGetScene = Il2.Method(gameObjectClass, "get_scene", 0);
        GameObjectGetActiveInHierarchy = Il2.Method(gameObjectClass, "get_activeInHierarchy", 0);

        TransformGetParent = Il2.Method(transformClass, "get_parent", 0);
        TransformGetChildCount = Il2.Method(transformClass, "get_childCount", 0);
        TransformGetChild = Il2.Method(transformClass, "GetChild", 1);
        TransformLocalPosition = Il2.Method(transformClass, "get_localPosition", 0);
        TransformLocalRotation = Il2.Method(transformClass, "get_localRotation", 0);
        TransformLocalScale = Il2.Method(transformClass, "get_localScale", 0);

        AnimatorIsHuman = Il2.Method(AnimatorClass, "get_isHuman", 0);
        AnimatorIsInitialized = Il2.Method(AnimatorClass, "get_isInitialized", 0);
        AnimatorGetAvatar = Il2.Method(AnimatorClass, "get_avatar", 0);
        AnimatorGetBoneTransform = Il2.Method(AnimatorClass, "GetBoneTransform", 1);
        AnimatorApplyRootMotion = Il2.Method(AnimatorClass, "get_applyRootMotion", 0);
        AnimatorUpdateMode = Il2.Method(AnimatorClass, "get_updateMode", 0);
        AnimatorCullingMode = Il2.Method(AnimatorClass, "get_cullingMode", 0);
        AnimatorController = Il2.Method(AnimatorClass, "get_runtimeAnimatorController", 0);
        AvatarIsValid = Il2.Method(avatarClass, "get_isValid", 0);
        AvatarIsHuman = Il2.Method(avatarClass, "get_isHuman", 0);

        SkinnedSharedMesh = Il2.Method(SkinnedClass, "get_sharedMesh", 0);
        SkinnedBones = Il2.Method(SkinnedClass, "get_bones", 0);
        SkinnedRootBone = Il2.Method(SkinnedClass, "get_rootBone", 0);
        SkinnedBlendShapeWeight = Il2.Method(SkinnedClass, "GetBlendShapeWeight", 1);
        RendererGetEnabled = Il2.Method(rendererClass, "get_enabled", 0);
        RendererSharedMaterials = Il2.Method(rendererClass, "get_sharedMaterials", 0);
        MaterialGetShader = Il2.Method(materialClass, "get_shader", 0);

        MeshBlendShapeCount = Il2.Method(meshClass, "get_blendShapeCount", 0);
        MeshGetBlendShapeName = Il2.Method(meshClass, "GetBlendShapeName", 1);
        MeshVertexCount = Il2.Method(meshClass, "get_vertexCount", 0);
        MeshSubMeshCount = Il2.Method(meshClass, "get_subMeshCount", 0);

        ResourcesFindObjectsOfTypeAll = Il2.MethodExact(resourcesClass, "FindObjectsOfTypeAll", "System.Type");
        GameObjectGetComponents = Il2.MethodExact(gameObjectClass, "GetComponents", "System.Type");
        ComponentTypeObject = Il2.TypeObject(componentClass);
        RendererTypeObject = Il2.TypeObject(rendererClass);
        SwingBoneTypeObject = Il2.TypeObject(Il2.FindClass("ActorAnimation", "ActorSwingDynamicBone"));
        TransformTypeObject = Il2.TypeObject(transformClass);
        SkinnedTypeObject = Il2.TypeObject(SkinnedClass);
        AnimatorTypeObject = Il2.TypeObject(AnimatorClass);
    }

    internal string Name(IntPtr unityObject) =>
        unityObject == IntPtr.Zero ? string.Empty : Il2.Str(Il2.Invoke(ObjectGetName, unityObject));

    internal string Path(IntPtr transform)
    {
        var names = new List<string>();
        for (var current = transform; current != IntPtr.Zero; current = Il2.Invoke(TransformGetParent, current))
        {
            names.Add(Name(current));
            if (names.Count > 64)
                break;
        }
        names.Reverse();
        return string.Join("/", names);
    }
}

[BepInPlugin(PluginGuid, PluginName, PluginVersion)]
public sealed class AvatarProbePlugin : BasePlugin
{
    public const string PluginGuid = "gakumas.avatar.probe";
    public const string PluginName = "Gakumas Avatar Probe";
    public const string PluginVersion = "0.20.0-opaque-fallback";

    internal static ManualLogSource LogSource = null!;
    internal static string OutputDirectory = string.Empty;
    private static string _bootLog = string.Empty;
    private static string _lastSignature = string.Empty;
    private static int _snapshotCount;
    private static UnityApi? _api;
    private static HashSet<string> _liveActors = new();
    private static readonly HashSet<string> DumpedClasses = new();
    private static readonly HashSet<string> DumpedRoots = new();

    private static readonly JsonSerializerOptions JsonOptions = new() { IncludeFields = true, WriteIndented = true };

    // ponytail: staged boot log written with raw File I/O — an AccessViolation kills the
    // process before BepInEx flushes its own sink, so the last line on disk is the crash site.
    internal static void Step(string message)
    {
        try { File.AppendAllText(_bootLog, $"{DateTime.Now:HH:mm:ss.fff} {message}{Environment.NewLine}"); }
        catch { /* boot log is best-effort */ }
    }

    public override void Load()
    {
        LogSource = Log;
        OutputDirectory = Path.Combine(Paths.ConfigPath, "gakumas-avatar-probe");
        Directory.CreateDirectory(OutputDirectory);
        _bootLog = Path.Combine(OutputDirectory, "boot.log");
        File.WriteAllText(_bootLog, $"{PluginName} {PluginVersion} Load() entered at {DateTime.Now:O}{Environment.NewLine}");

        Step("s1 images and classes ...");
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var objectClass = Il2.Class(core, "UnityEngine", "Object");
        Step($"s1 ok: core={core:X} GameObject={gameObjectClass:X} Object={objectClass:X}");

        Step("s2 raw new GameObject(name) ...");
        var host = Il2.il2cpp_object_new(gameObjectClass);
        Il2.Invoke(Il2.Method(gameObjectClass, ".ctor", 1), host, Il2.il2cpp_string_new("GakumasAvatarProbe"));
        Step($"s2 ok: host={host:X}");

        Step("s3 raw DontDestroyOnLoad ...");
        Il2.Invoke(Il2.Method(objectClass, "DontDestroyOnLoad", 1), IntPtr.Zero, host);
        Step("s3 ok");

        Step("s4 ClassInjector.RegisterTypeInIl2Cpp<ProbeBehaviour> ...");
        ClassInjector.RegisterTypeInIl2Cpp<ProbeBehaviour>();
        var probeClass = Il2CppClassPointerStore<ProbeBehaviour>.NativeClassPtr;
        Step($"s4 ok: injected={probeClass:X}");

        Step("s5 raw AddComponent(injected) ...");
        var component = Il2.Invoke(Il2.Method(gameObjectClass, "AddComponent", 1), host, Il2.TypeObject(probeClass));
        Step($"s5 ok: component={component:X}");

        Step("s6 install hooks ...");
        try { InstallHooks(); Step("s6 ok"); }
        catch (Exception exception) { Step($"s6 failed (probe continues without hooks): {exception}"); }

        Step("Load() complete — waiting for Update() ticks");
        Log.LogInfo($"{PluginName} loaded.");
    }

    // IL2CPP passes MethodInfo* as a trailing argument to every compiled method, so every hook
    // delegate carries it even when the managed signature does not.
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void BuildAvatarDelegate(IntPtr self, IntPtr methodInfo);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void BuildModelDelegate(IntPtr self, IntPtr resources, IntPtr methodInfo);

    private static BuildAvatarDelegate? _buildAvatarOriginal;
    private static BuildModelDelegate? _buildModelOriginal;
    private static readonly List<object> DetourRoots = new();
    private static string _hookLog = string.Empty;

    private static void Hook(string message)
    {
        try { File.AppendAllText(_hookLog, $"{DateTime.Now:HH:mm:ss.fff} {message}{Environment.NewLine}"); }
        catch { /* best effort */ }
    }

    // Log-only for now: prove the detour path works and see exactly what the actor build is
    // handed, before anything is substituted.
    private static void InstallHooks()
    {
        _hookLog = Path.Combine(OutputDirectory, "hooks.log");
        // swap-experiment.txt: line 1 = bundle file path, line 2 = asset name inside it.
        // Empty file = donate the first actor's own body instead (no external bundle).
        var swapConfig = Path.Combine(OutputDirectory, "swap-experiment.txt");
        _swapEnabled = File.Exists(swapConfig);
        if (_swapEnabled)
        {
            // key=value lines: bundle / asset / source / dependency (dependency may repeat).
            foreach (var raw in File.ReadAllLines(swapConfig))
            {
                var line = raw.Trim();
                var split = line.IndexOf('=');
                if (line.Length == 0 || line[0] == '#' || split <= 0)
                    continue;
                var key = line.Substring(0, split).Trim();
                var value = line.Substring(split + 1).Trim();
                switch (key)
                {
                    case "bundle": _bundlePath = value; break;
                    case "asset": _bundleAsset = value; break;
                    case "source": _sourceAsset = value; break;
                    // A/B control: run once with the components attached and once without, so
                    // "the mod's bones move" can be attributed instead of assumed.
                    case "swing": _attachSwing = value != "off"; break;
                    // Absent or `off` keeps the source mesh's COLOR, which is the default.
                    case "color":
                        var parts = value.Split(',');
                        if (parts.Length != 4)
                            break;
                        var flattened = new float[4];
                        for (var channel = 0; channel < 4; channel++)
                            flattened[channel] = float.Parse(parts[channel].Trim(), System.Globalization.CultureInfo.InvariantCulture);
                        _vertexColor = flattened;
                        break;
                    case "dependency": _dependencyBundles.Add(value); break;
                }
            }
        }
        Step($"hook: swap {(_swapEnabled ? "ENABLED" : "off")} source={_sourceAsset} bundle={_bundlePath} asset={_bundleAsset}");
        var controller = Il2.FindClass("Campus.Common", "CampusActorController");
        Step($"hook: CampusActorController={controller:X}");

        // Each hook installs independently: one unresolved target must not skip the others.
        Install("BuildAvatar", () =>
        {
            var target = Il2.CodePointer(Il2.Method(controller, "BuildAvatar", 0));
            DetourRoots.Add(INativeDetour.CreateAndApply<BuildAvatarDelegate>(target, OnBuildAvatar, out _buildAvatarOriginal));
            return target;
        });

        Install("BuildModel", () =>
        {
            var target = Il2.CodePointer(Il2.MethodExact(controller, "BuildModel", "System.Collections.Generic.IEnumerable<UnityEngine.GameObject>"));
            DetourRoots.Add(INativeDetour.CreateAndApply<BuildModelDelegate>(target, OnBuildModel, out _buildModelOriginal));
            return target;
        });
    }

    private static void Install(string name, Func<IntPtr> install)
    {
        try { Step($"hook: {name} @ {install():X}"); }
        catch (Exception exception) { Step($"hook: {name} FAILED: {exception.Message}"); }
    }

    private static void OnBuildAvatar(IntPtr self, IntPtr methodInfo)
    {
        try { Hook($"BuildAvatar self={self:X} {(_api == null ? string.Empty : _api.Name(self))}"); }
        catch (Exception exception) { Hook($"BuildAvatar log failed: {exception.Message}"); }
        _buildAvatarOriginal!(self, methodInfo);
    }

    // Swap experiment: hand the second actor the first actor's body prefab. Both are known-good
    // game assets, so a success proves the whole downstream (parts, bone map, BuildAvatar, swing
    // drivers) accepts a foreign prefab — with no home-made bundle in the picture yet.
    // Enabled only when swap-experiment.txt exists next to the logs.
    private static bool _swapEnabled;
    private static IntPtr _donorBody;
    private static string _donorName = string.Empty;
    private static bool _swapDone;
    private static string _bundlePath = string.Empty;
    private static string _bundleAsset = string.Empty;
    private static string _sourceAsset = string.Empty;
    private static bool _attachSwing = true;
    private static readonly List<string> _dependencyBundles = new();

    private static void OnBuildModel(IntPtr self, IntPtr resources, IntPtr methodInfo)
    {
        try
        {
            var api = _api;
            Hook($"BuildModel self={self:X} resources={(api == null ? $"{resources:X}" : Il2.Describe(resources, api.Name))}");
            if (api != null && _swapEnabled && !_swapDone)
                TrySwapBody(api, resources);
        }
        catch (Exception exception) { Hook($"BuildModel hook failed: {exception.Message}"); }
        _buildModelOriginal!(self, resources, methodInfo);
    }

    // Load a prefab out of a bundle file of our own. AssetBundle.LoadFromFile (sync) is stripped
    // from the shipped build, but reading AssetBundleCreateRequest.assetBundle forces the async
    // load to complete synchronously, which gets us the same thing.
    // Unity refuses a second LoadFromFile* of an already-loaded file ("The AssetBundle ... can't be
    // loaded because another AssetBundle with the same files is already loaded"), so every path is
    // opened at most once per process. Nothing is ever unloaded — see the leak note below.
    private static readonly Dictionary<string, IntPtr> LoadedBundles = new();

    private static IntPtr LoadBundle(string bundlePath)
    {
        if (LoadedBundles.TryGetValue(bundlePath, out var cached))
            return cached;
        var module = Il2.Image("UnityEngine.AssetBundleModule");
        var bundleClass = Il2.Class(module, "UnityEngine", "AssetBundle");
        var requestClass = Il2.Class(module, "UnityEngine", "AssetBundleCreateRequest");
        var request = Il2.Invoke(Il2.MethodExact(bundleClass, "LoadFromFileAsync", "System.String"),
            IntPtr.Zero, Il2.il2cpp_string_new(bundlePath));
        if (request == IntPtr.Zero)
            throw new InvalidOperationException($"LoadFromFileAsync returned null for {bundlePath}");
        var bundle = Il2.Invoke(Il2.Method(requestClass, "get_assetBundle", 0), request);
        if (bundle == IntPtr.Zero)
            throw new InvalidOperationException($"bundle failed to load: {bundlePath}");
        LoadedBundles[bundlePath] = bundle;
        return bundle;
    }

    private static IntPtr LoadPrefabFromBundle(string bundlePath, string assetName)
    {
        var module = Il2.Image("UnityEngine.AssetBundleModule");
        var bundleClass = Il2.Class(module, "UnityEngine", "AssetBundle");
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectType = Il2.TypeObject(Il2.Class(core, "UnityEngine", "GameObject"));

        // AssetBundle dependencies are not resolved automatically; load them first or the
        // materials come back with a missing shader.
        foreach (var dependency in _dependencyBundles)
            Hook($"dependency {Path.GetFileName(dependency)} -> {LoadBundle(dependency):X}");

        var bundle = LoadBundle(bundlePath);
        var prefab = Il2.Invoke(Il2.MethodExact(bundleClass, "LoadAsset", "System.String", "System.Type"),
            bundle, Il2.il2cpp_string_new(assetName), gameObjectType);
        if (prefab == IntPtr.Zero)
            throw new InvalidOperationException($"asset {assetName} not found in {bundlePath}");
        return prefab;
    }

    // Original body prefabs carry no game components at all, so the swing chains must be derived
    // at runtime from bone naming (`_S` swing, `_H` volume, `_Roll_H` twist). This injects a bone
    // into an otherwise untouched original prefab to find out how much structural freedom a mod
    // actually has — no bundle authoring needed to answer that.
    private static void InjectTestBone(UnityApi api, IntPtr prefab, string parentBoneName, string newBoneName)
    {
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var transformClass = Il2.Class(core, "UnityEngine", "Transform");

        // get_transform, not GetComponent(Type): fewer invokes, and no chance of feeding a null
        // instance into the next call — which is exactly what access-violated here.
        var prefabTransform = Il2.Invoke(Il2.Method(gameObjectClass, "get_transform", 0), prefab);
        if (prefabTransform == IntPtr.Zero)
        {
            Hook("inject: prefab has no transform");
            return;
        }
        // Prefabs loaded from a bundle are ordinary inactive objects in a player build.
        var transforms = Il2.Invoke(api.ComponentGetComponentsInChildren, prefabTransform, api.TransformTypeObject, Il2.Arg(true));
        Hook($"inject: prefab transform={prefabTransform:X} children={Il2.Length(transforms)}");

        var parent = IntPtr.Zero;
        for (var index = 0; index < Il2.Length(transforms); index++)
        {
            var candidate = Il2.Item(transforms, index);
            if (candidate != IntPtr.Zero && api.Name(candidate) == parentBoneName)
            {
                parent = candidate;
                break;
            }
        }
        if (parent == IntPtr.Zero)
        {
            Hook($"inject: parent bone {parentBoneName} not found among {Il2.Length(transforms)} transforms");
            return;
        }

        var bone = Il2.il2cpp_object_new(gameObjectClass);
        Il2.Invoke(Il2.Method(gameObjectClass, ".ctor", 1), bone, Il2.il2cpp_string_new(newBoneName));
        var boneTransform = Il2.Invoke(Il2.Method(gameObjectClass, "get_transform", 0), bone);
        if (boneTransform == IntPtr.Zero)
        {
            Hook("inject: new bone has no transform");
            return;
        }
        Il2.Invoke(Il2.MethodExact(transformClass, "SetParent", "UnityEngine.Transform", "System.Boolean"),
            boneTransform, parent, Il2.Arg(false));
        Hook($"inject: {newBoneName} attached under {parentBoneName}");
    }

    // A mod prefab built outside the game has no game MonoBehaviours, so the actor build crashes
    // later in InitializeActorAnimation with a null part. VLActorModelParts populates itself at
    // runtime (Initialize/ProcessBones/UpdateSkinnedMeshRenderers), so the component only has to
    // exist — the bone info does not need to be baked into the bundle.
    private static void EnsureModelParts(IntPtr modPrefab, IntPtr originalPrefab)
    {
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var getComponent = Il2.MethodExact(gameObjectClass, "GetComponent", "System.Type");
        var addComponent = Il2.MethodExact(gameObjectClass, "AddComponent", "System.Type");
        var partsType = Il2.TypeObject(Il2.FindClass("Campus.Common", "CampusActorModelParts"));

        Hook($"parts: original prefab has CampusActorModelParts = {Il2.Invoke(getComponent, originalPrefab, partsType):X}");
        var existing = Il2.Invoke(getComponent, modPrefab, partsType);
        if (existing != IntPtr.Zero)
        {
            Hook($"parts: mod prefab already has one = {existing:X}");
            return;
        }
        Hook($"parts: added to mod prefab = {Il2.Invoke(addComponent, modPrefab, partsType):X}");
    }

    private static readonly string[] TextureSlots = { "_BaseMap", "_DefMap", "_ShadeMap" };

    // This game reads vertex COLOR as data, not as a tint: it drives the outline and picks the
    // RampAdd row from the low nibble of G.
    //
    // Off by default — the source mesh's own COLOR is kept. Flattening every vertex to one value
    // was a workaround from when the materials still carried the wrong shader and no textures; it
    // costs the per-material distinction the ramp row encodes, so bare skin ends up on the cloth
    // ramp and goes grey. Opt in with `color=r,g,b,a` in swap-experiment.txt when a foreign mesh
    // really does land on the wrong ramp (the neon-green wings); `color=off` or no line keeps it.
    private static float[]? _vertexColor;

    private static void NormalizeVertexColors(UnityApi api, IntPtr modPrefab)
    {
        if (_vertexColor == null)
        {
            Hook("colors: 保留源网格 COLOR（未配置 color=）");
            return;
        }
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var meshClass = Il2.Class(core, "UnityEngine", "Mesh");
        var colorClass = Il2.Class(core, "UnityEngine", "Color");

        var renderer = FirstRenderer(api, Il2.Invoke(Il2.Method(gameObjectClass, "get_transform", 0), modPrefab));
        if (renderer == IntPtr.Zero)
        {
            Hook("colors: no renderer");
            return;
        }
        var mesh = Il2.Invoke(api.SkinnedSharedMesh, renderer);
        if (mesh == IntPtr.Zero)
        {
            Hook("colors: renderer has no mesh");
            return;
        }
        var count = Il2.Int(Il2.Invoke(api.MeshVertexCount, mesh));
        if (count <= 0)
        {
            Hook("colors: mesh has no vertices");
            return;
        }

        // Color is a 4-float struct, so the array payload is written inline.
        var colors = Il2.il2cpp_array_new(colorClass, (ulong)count);
        for (var index = 0; index < count; index++)
        {
            var at = 0x20 + index * 16;
            for (var channel = 0; channel < 4; channel++)
                Marshal.WriteInt32(colors, at + channel * 4, BitConverter.SingleToInt32Bits(_vertexColor[channel]));
        }
        Il2.Invoke(Il2.Method(meshClass, "set_colors", 1), mesh, colors);
        Hook($"colors: flattened {count} vertices to ({string.Join(", ", _vertexColor)})");
    }

    // Swing components live on the individual bones, and a foreign prefab's are compiled against
    // the other game's namespace so the player drops them. Re-attach this game's own component to
    // every `_S` bone, with the parameter set the game's own costumes use.
    // rootWeight and pendulum must be written explicitly: their defaults (1.0 / 0) mean
    // "locked, no droop", i.e. a bone that never moves.
    private static void AddSwingBones(UnityApi api, IntPtr modPrefab)
    {
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var swingClass = Il2.FindClass("ActorAnimation", "ActorSwingDynamicBone");
        var swingType = Il2.TypeObject(swingClass);
        var addComponent = Il2.MethodExact(gameObjectClass, "AddComponent", "System.Type");
        var getGameObject = api.ComponentGetGameObject;

        var floats = new (string Field, float Value)[]
        {
            ("damping", 0.4f), ("stiffness", 0.02f), ("spring", 0.5f), ("mass", 0.6f),
            ("pendulum", 0.003f), ("pendulumRange", 1.0f), ("rootWeight", 0.3f), ("wind", 1.0f),
        };

        var prefabTransform = Il2.Invoke(Il2.Method(gameObjectClass, "get_transform", 0), modPrefab);
        var transforms = Il2.Invoke(api.ComponentGetComponentsInChildren, prefabTransform, api.TransformTypeObject, Il2.Arg(true));
        var added = 0;
        for (var index = 0; index < Il2.Length(transforms); index++)
        {
            var bone = Il2.Item(transforms, index);
            if (bone == IntPtr.Zero || !api.Name(bone).EndsWith("_S", StringComparison.Ordinal))
                continue;
            var component = Il2.Invoke(addComponent, Il2.Invoke(getGameObject, bone), swingType);
            if (component == IntPtr.Zero)
                continue;
            foreach (var (field, value) in floats)
            {
                var handle = Il2.il2cpp_class_get_field_from_name(swingClass, field);
                if (handle == IntPtr.Zero)
                    continue;
                Il2.SetFloat(component, handle, value);
            }
            added++;
        }
        Hook($"swing: attached ActorSwingDynamicBone to {added} `_S` bones");
    }

    // The mod prefab's materials point at a shader this game does not have, so they render magenta;
    // the game's materials carry the right shader plus shared ramps. Both projects use the same
    // property names, so clone the game's material and move the mod's textures onto it — no name
    // guessing, and _RampMap/_RampAddMap stay as the game authored them.
    private static void RebuildMaterials(UnityApi api, IntPtr modPrefab, IntPtr originalPrefab)
    {
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var materialClass = Il2.Class(core, "UnityEngine", "Material");
        var shaderClass = Il2.Class(core, "UnityEngine", "Shader");
        var getTransform = Il2.Method(gameObjectClass, "get_transform", 0);

        var propertyToId = Il2.MethodExact(shaderClass, "PropertyToID", "System.String");
        var getTexture = Il2.MethodExact(materialClass, "GetTextureImpl", "System.Int32");
        var setTexture = Il2.MethodExact(materialClass, "SetTextureImpl", "System.Int32", "UnityEngine.Texture");
        var copyConstructor = Il2.MethodExact(materialClass, ".ctor", "UnityEngine.Material");

        var slotIds = new int[TextureSlots.Length];
        for (var index = 0; index < TextureSlots.Length; index++)
            slotIds[index] = Il2.Int(Il2.Invoke(propertyToId, IntPtr.Zero, Il2.il2cpp_string_new(TextureSlots[index])));

        var originalRenderer = FirstRenderer(api, Il2.Invoke(getTransform, originalPrefab));
        var modRenderer = FirstRenderer(api, Il2.Invoke(getTransform, modPrefab));
        if (originalRenderer == IntPtr.Zero || modRenderer == IntPtr.Zero)
        {
            Hook($"materials: renderer not found (original={originalRenderer:X} mod={modRenderer:X})");
            return;
        }

        var originalMaterials = Il2.Invoke(api.RendererSharedMaterials, originalRenderer);
        var modMaterials = Il2.Invoke(api.RendererSharedMaterials, modRenderer);
        var originalCount = Il2.Length(originalMaterials);
        var slots = Il2.Length(modMaterials);
        if (originalCount == 0 || slots == 0)
        {
            Hook($"materials: nothing to work with (original={originalCount} mod={slots})");
            return;
        }

        var rebuilt = Il2.il2cpp_array_new(materialClass, (ulong)slots);
        for (var slot = 0; slot < slots; slot++)
        {
            var modMaterial = Il2.Item(modMaterials, slot);
            var modName = Clean(api.Name(modMaterial));

            // Match by name (m_bdy/m_bdyco). An unmatched slot falls back to the *first* vanilla
            // material, not the last: the last one is typically `m_bdyco`, which is alpha-tested
            // (`_ALPHATEST_ON`, `_Cutoff` 0.5), so every extra section a mod brings used to be
            // clipped away wholesale. `m_bdy` is the plain opaque body material — the right default
            // for a section we know nothing about.
            var template = Il2.Item(originalMaterials, 0);
            for (var candidate = 0; candidate < originalCount; candidate++)
            {
                if (Clean(api.Name(Il2.Item(originalMaterials, candidate))) != modName)
                    continue;
                template = Il2.Item(originalMaterials, candidate);
                break;
            }

            var clone = Il2.il2cpp_object_new(materialClass);
            Il2.Invoke(copyConstructor, clone, template);

            var moved = new List<string>();
            for (var index = 0; index < slotIds.Length; index++)
            {
                if (modMaterial == IntPtr.Zero)
                    break;
                var texture = Il2.Invoke(getTexture, modMaterial, Il2.Arg(slotIds[index]));
                if (texture == IntPtr.Zero)
                    continue;
                Il2.Invoke(setTexture, clone, Il2.Arg(slotIds[index]), texture);
                moved.Add($"{TextureSlots[index]}={api.Name(texture)}");
            }
            Il2.SetItem(rebuilt, slot, clone);
            Hook($"materials: slot {slot} {modName} <- {Clean(api.Name(template))} [{string.Join(", ", moved)}]");
        }

        Il2.Invoke(Il2.Method(Il2.Class(core, "UnityEngine", "Renderer"), "set_sharedMaterials", 1), modRenderer, rebuilt);
    }

    // A prefab authored in a plain Unity project comes out on layer 0, and the game's cameras do
    // not draw that layer — the body is fully built, correctly skinned, materials right, and simply
    // never appears. The layer number is the game's business, not the author's, so take it from the
    // part being replaced instead of asking the SDK to hardcode one.
    private static void CopyLayer(UnityApi api, IntPtr modPrefab, IntPtr originalPrefab)
    {
        var core = Il2.Image("UnityEngine.CoreModule");
        var gameObjectClass = Il2.Class(core, "UnityEngine", "GameObject");
        var getTransform = Il2.Method(gameObjectClass, "get_transform", 0);
        var getLayer = Il2.Method(gameObjectClass, "get_layer", 0);
        var setLayer = Il2.Method(gameObjectClass, "set_layer", 1);

        var layer = Il2.Int(Il2.Invoke(getLayer, originalPrefab));
        var transforms = Il2.Invoke(api.ComponentGetComponentsInChildren, Il2.Invoke(getTransform, modPrefab),
            api.TransformTypeObject, Il2.Arg(true));
        var applied = 0;
        for (var index = 0; index < Il2.Length(transforms); index++)
        {
            var transform = Il2.Item(transforms, index);
            if (transform == IntPtr.Zero)
                continue;
            Il2.Invoke(setLayer, Il2.Invoke(api.ComponentGetGameObject, transform), Il2.Arg(layer));
            applied++;
        }
        Hook($"layer: {applied} 个节点设为 {layer}（来自原版部件）");
    }

    // Scalars and colours the game writes per scene / per actor, plus the render-state ones that
    // decide whether a draw lands at all. Read as "name=value" strings so a diff between our body
    // and the stock face is eyeballable straight out of the JSON.
    private static readonly string[] MaterialFloats =
    {
        "_ActorIndex", "_ColorMask", "_StencilRef", "_StencilComp", "_StencilPass",
        "_StencilReadMask", "_StencilWriteMask", "_Blend", "_Mode", "_ShaderType", "_RenderMode",
        "_Surface", "_Cull", "_ZWrite", "_AlphaClip", "_Cutoff", "_Metallic", "_Smoothness",
        "_EnableLayerMap", "_LayerWeight", "_SpecularAdd", "_EnableEmission",
    };

    private static readonly string[] MaterialColors =
    {
        "_BaseColor", "_MultiplyColor", "_ShadeColor", "_RimColor", "_RampAddColor",
        "_OutlineColor", "_MultiplyOutlineColor", "_SpecColor", "_DefValue", "_FadeParam",
        "_LineDefParam", "_SpecularThreshold",
    };

    private static string[] ReadMaterialProperties(IntPtr material)
    {
        if (material == IntPtr.Zero)
            return Array.Empty<string>();
        var core = Il2.Image("UnityEngine.CoreModule");
        var materialClass = Il2.Class(core, "UnityEngine", "Material");
        var shaderClass = Il2.Class(core, "UnityEngine", "Shader");
        var propertyToId = Il2.MethodExact(shaderClass, "PropertyToID", "System.String");
        var getFloat = Il2.MethodExact(materialClass, "GetFloatImpl", "System.Int32");
        var getColor = Il2.MethodExact(materialClass, "GetColorImpl", "System.Int32");
        var hasProperty = Il2.MethodExact(materialClass, "HasProperty", "System.Int32");

        var values = new List<string>();
        foreach (var name in MaterialFloats)
        {
            var id = Il2.Arg(Il2.Int(Il2.Invoke(propertyToId, IntPtr.Zero, Il2.il2cpp_string_new(name))));
            if (!Il2.Bool(Il2.Invoke(hasProperty, material, id)))
                continue;
            values.Add($"{name}={Il2.Float(Il2.Invoke(getFloat, material, id)):0.####}");
        }
        foreach (var name in MaterialColors)
        {
            var id = Il2.Arg(Il2.Int(Il2.Invoke(propertyToId, IntPtr.Zero, Il2.il2cpp_string_new(name))));
            if (!Il2.Bool(Il2.Invoke(hasProperty, material, id)))
                continue;
            var color = Il2.Invoke(getColor, material, id);
            values.Add($"{name}=({Il2.FloatAt(color, 0):0.###},{Il2.FloatAt(color, 4):0.###}," +
                       $"{Il2.FloatAt(color, 8):0.###},{Il2.FloatAt(color, 12):0.###})");
        }
        return values.ToArray();
    }

    private static string Clean(string materialName)
    {
        var marker = materialName.IndexOf(" (Instance)", StringComparison.Ordinal);
        return marker < 0 ? materialName : materialName.Substring(0, marker);
    }

    private static IntPtr FirstRenderer(UnityApi api, IntPtr transform)
    {
        if (transform == IntPtr.Zero)
            return IntPtr.Zero;
        var found = Il2.Invoke(api.ComponentGetComponentsInChildren, transform, api.RendererTypeObject, Il2.Arg(true));
        return Il2.Length(found) == 0 ? IntPtr.Zero : Il2.Item(found, 0);
    }

    private static void TrySwapBody(UnityApi api, IntPtr resources)
    {
        for (var index = 0; index < Il2.Length(resources); index++)
        {
            var item = Il2.Item(resources, index);
            if (item == IntPtr.Zero)
                continue;
            var name = api.Name(item);

            // Replace by the asset the game asked for, so every actor wearing that costume gets
            // the mod — not just whichever one happens to build first.
            var matches = _sourceAsset.Length > 0
                ? name == _sourceAsset
                : name.EndsWith("_body", StringComparison.Ordinal);
            if (!matches)
                continue;

            // "inject" mode: leave the original prefab in place and only add a bone to it.
            if (_bundlePath == "inject")
            {
                InjectTestBone(api, item, _bundleAsset, "TestSkirt1_S");
                _swapDone = true;
                return;
            }

            if (_donorBody == IntPtr.Zero)
            {
                if (_bundlePath.Length == 0)
                {
                    // No bundle configured: fall back to donating the first actor's own body.
                    _donorBody = item;
                    _donorName = name;
                    Hook($"swap: donor captured from scene {name}");
                    return;
                }
                _donorBody = LoadPrefabFromBundle(_bundlePath, _bundleAsset);
                _donorName = $"{_bundleAsset} (from file)";
                Hook($"swap: donor loaded {_donorName} ptr={_donorBody:X}");
                EnsureModelParts(_donorBody, item);
                // No Head_Hair / Head_Face anchors here: the hair and face parts bring their own,
                // and the bone-name map is global across parts — adding them collides
                // ("An item with the same key has already been added. Key: Head_Face").
                try { NormalizeVertexColors(api, _donorBody); }
                catch (Exception exception) { Hook($"colors: failed {exception.Message}"); }
                if (_attachSwing)
                    try { AddSwingBones(api, _donorBody); }
                    catch (Exception exception) { Hook($"swing: failed {exception.Message}"); }
                else
                    Hook("swing: 按配置跳过挂载（对照组）");
            }

            // Every build, not just the first. The clone freezes whatever the template material held
            // at clone time, and two of its slots do not survive a scene change: frame analysis of the
            // 撮影 scene shows our body drawn with t3 (`_RampMap`, the shared 1024×4 toon ramp) and t5
            // (`_RampAddMap`, the costume's 128×16 strip) *unbound*, while stock parts in the same
            // frame have both — an unbound SRV samples as 0, which is why the skin turns black there
            // and looks right in 换装. The content hashes are identical across scenes, so the game
            // re-creates these per scene and re-runs its own material init (`CampusActorModelParts.
            // InitializeCampusMaterials`) on the parts it builds; a clone made in an earlier scene is
            // left holding dead references. Re-cloning from the live template each build picks up
            // whatever that scene assigned.
            // ponytail: leaks the previous clones (3 materials per rebuild). Destroying them risks
            // freeing something the renderer still points at; revisit if memory actually bites.
            try { CopyLayer(api, _donorBody, item); }
            catch (Exception exception) { Hook($"layer: failed {exception.Message}"); }
            try { RebuildMaterials(api, _donorBody, item); }
            catch (Exception exception) { Hook($"materials: failed {exception.Message}"); }

            Il2.SetItem(resources, index, _donorBody);
            Hook($"swap: {name} -> {_donorName}");
            return;
        }
    }

    // Called from the injected MonoBehaviour, on the Unity main thread.
    internal static void Scan(int frame)
    {
        if (_api == null)
        {
            _api = new UnityApi();
            Step("api resolved");
        }
        var api = _api;

        var found = Il2.Invoke(api.ResourcesFindObjectsOfTypeAll, IntPtr.Zero, api.AnimatorTypeObject);
        var count = Il2.Length(found);

        // Cheap pass every tick: identity only. The full walk below costs thousands of invokes,
        // so it must not run at tick rate — it runs when the set of live actors changes.
        var candidates = new List<(IntPtr Animator, IntPtr GameObject, int Scene, string Path)>();
        var skipped = 0;
        for (var index = 0; index < count; index++)
        {
            var animator = Il2.Item(found, index);
            if (animator == IntPtr.Zero)
                continue;
            // FindObjectsOfTypeAll also returns prefabs and other assets; a live instance has a
            // valid scene handle. Anything else is a template, not ground truth.
            var gameObject = Il2.Invoke(api.ComponentGetGameObject, animator);
            var sceneHandle = Il2.Int(Il2.Invoke(api.GameObjectGetScene, gameObject));
            if (sceneHandle == 0)
            {
                skipped++;
                continue;
            }
            candidates.Add((animator, gameObject, sceneHandle, api.Path(Il2.Invoke(api.ComponentGetTransform, animator))));
        }

        var live = new HashSet<string>();
        foreach (var candidate in candidates)
            live.Add(candidate.Path);
        Timeline(frame, live);
        foreach (var candidate in candidates)
        {
            ReportSwingMotion(api, frame, candidate.Animator, candidate.Path);
            try { DumpSwingReference(api, candidate.Animator, candidate.Path); }
            catch (Exception exception) { Hook($"swing reference failed: {exception.Message}"); }
        }

        var signature = string.Join("\n", live);
        if (signature == _lastSignature)
            return;
        _lastSignature = signature;

        var animators = new List<AnimatorProbe>(candidates.Count);
        var actorRoots = new List<IntPtr>(candidates.Count);
        foreach (var candidate in candidates)
        {
            animators.Add(ProbeAnimator(api, candidate.Animator, candidate.GameObject, candidate.Scene));
            actorRoots.Add(candidate.GameObject);
        }
        DumpComponents(api, actorRoots);

        var path = Path.Combine(OutputDirectory, $"{DateTime.Now:yyyyMMdd-HHmmssfff}-avatars.json");
        File.WriteAllText(path, JsonSerializer.Serialize(new ProbeSnapshot
        {
            utc = DateTime.UtcNow.ToString("O"),
            frame = frame,
            foundTotal = count,
            skippedNonScene = skipped,
            animators = animators.ToArray(),
        }, JsonOptions));
        _snapshotCount++;
        Step($"scan#{_snapshotCount} frame={frame} scene={animators.Count} skipped={skipped} -> {Path.GetFileName(path)}");
    }

    private static readonly HashSet<string> SwingReferenceDumped = new();

    // Attaching ActorSwingDynamicBone alone does not make a bone move; the stock costumes pair
    // ~82 dynamic bones with only 3 ActorSwingChain components, so the chain is what drives them.
    // Rather than guess the wiring, dump it off an untouched actor and copy what is actually there.
    private static void DumpSwingReference(UnityApi api, IntPtr animator, string actorPath)
    {
        var actor = actorPath.Split('|')[0].Trim();
        if (SwingReferenceDumped.Contains(actor))
            return;
        // The camera has no swing at all; dumping from it burned a whole run. Require components,
        // and write one file per actor rather than stopping after the first — whichever character
        // is on screen next, a stock one gets captured.
        var probe = Il2.Invoke(api.ComponentGetComponentsInChildren, animator, api.SwingBoneTypeObject, Il2.Arg(true));
        if (Il2.Length(probe) == 0)
            return;

        var text = new System.Text.StringBuilder();
        text.AppendLine($"# 原版角色摇物接线参考 {actorPath} @ {DateTime.Now:O}");

        foreach (var (ns, klass, limit) in new[]
                 {
                     ("ActorAnimation", "ActorSwingChain", 4),
                     ("ActorAnimation", "ActorSwingDynamicBone", 3),
                     ("ActorAnimation", "ActorSwingStaticBone", 2),
                     // Not swing, but the same problem: the bundles carry no type tree, so the only
                     // place the stock parameters exist is a live actor. A null hand correction goal
                     // aborts BuildAvatar from inside the Burst job.
                     ("ActorAnimation", "ActorAnimationIKCorrectionGoal", 2),
                     ("ActorAnimation", "ActorAnimationIKCorrectionCollider", 2),
                 })
        {
            IntPtr typeObject;
            try { typeObject = Il2.TypeObject(Il2.FindClass(ns, klass)); }
            catch (Exception exception) { text.AppendLine($"== {klass} 解析失败: {exception.Message}"); continue; }

            var found = Il2.Invoke(api.ComponentGetComponentsInChildren, animator, typeObject, Il2.Arg(true));
            var count = Il2.Length(found);
            text.AppendLine();
            text.AppendLine($"== {ns}.{klass}  共 {count} 个，下面列前 {Math.Min(limit, count)} 个");
            for (var index = 0; index < Math.Min(limit, count); index++)
            {
                var component = Il2.Item(found, index);
                if (component == IntPtr.Zero)
                    continue;
                var owner = Il2.Invoke(api.ComponentGetGameObject, component);
                text.AppendLine($"--- 挂在骨: {api.Name(owner)}");
                Il2.DumpInstance(component, 1, text, "   ", api.Name);
            }
        }

        SwingReferenceDumped.Add(actor);
        WriteDump("swing-reference", actor, text.ToString());
        Hook($"swing reference dumped: {actor}");
    }

    private static readonly Dictionary<string, float[]> SwingRotations = new();
    private static readonly Dictionary<string, int> SwingReported = new();

    // "Does it actually swing" is not answerable by eye on an idle character, and eyeballing a
    // screenshot cannot tell a driven bone from a rigid one. Measure it: sample every `_S` bone's
    // local rotation each tick and report how many of them actually moved.
    private static void ReportSwingMotion(UnityApi api, int frame, IntPtr animator, string actorPath)
    {
        var swingComponents = 0;
        try
        {
            var attached = Il2.Invoke(api.ComponentGetComponentsInChildren, animator, api.SwingBoneTypeObject, Il2.Arg(true));
            swingComponents = Il2.Length(attached);
        }
        catch (Exception) { /* class may not resolve on an untouched actor */ }

        var bones = Il2.Invoke(api.ComponentGetComponentsInChildren, animator, api.TransformTypeObject, Il2.Arg(true));
        var moved = 0;
        var tracked = 0;
        var largest = 0f;
        // Naming the busiest bones is what separates "the hair is swinging" from "the mod's own
        // bones are swinging" — the wings and tails have names no stock part uses.
        var top = new List<(float Delta, string Name)>();
        for (var index = 0; index < Il2.Length(bones); index++)
        {
            var bone = Il2.Item(bones, index);
            if (bone == IntPtr.Zero)
                continue;
            var name = api.Name(bone);
            if (!name.EndsWith("_S", StringComparison.Ordinal))
                continue;
            tracked++;
            var rotation = Il2.Floats(Il2.Invoke(api.TransformLocalRotation, bone), 4);
            var key = $"{actorPath}/{name}";
            if (SwingRotations.TryGetValue(key, out var previous))
            {
                var delta = 0f;
                for (var channel = 0; channel < 4; channel++)
                    delta += Math.Abs(rotation[channel] - previous[channel]);
                if (delta > 0.0005f)
                {
                    moved++;
                    top.Add((delta, name));
                }
                largest = Math.Max(largest, delta);
            }
            SwingRotations[key] = rotation;
        }
        if (tracked == 0)
            return;
        top.Sort((left, right) => right.Delta.CompareTo(left.Delta));

        // Only log when the picture changes, so the file stays readable across a long session.
        var signature = moved * 100000 + tracked * 100 + Math.Min(99, top.Count);
        if (SwingReported.TryGetValue(actorPath, out var last) && last == signature)
            return;
        SwingReported[actorPath] = signature;
        var busiest = string.Join(", ", top.GetRange(0, Math.Min(5, top.Count)).ConvertAll(entry => $"{entry.Name}:{entry.Delta:F3}"));
        Hook($"swingmotion: {actorPath.Split('|')[0].Trim()} frame={frame} `_S`骨={tracked} 组件={swingComponents} 移动={moved} 最大Δ={largest:F4} | {busiest}");
    }

    // Which actors exist, and when they appear or go away. This is the only thing that runs at
    // tick rate, so replacement hooks can later be aimed at a known point in the lifecycle.
    private static void Timeline(int frame, HashSet<string> live)
    {
        var lines = new List<string>();
        foreach (var path in live)
            if (!_liveActors.Contains(path))
                lines.Add($"{DateTime.Now:HH:mm:ss.fff} frame={frame} + {path}");
        foreach (var path in _liveActors)
            if (!live.Contains(path))
                lines.Add($"{DateTime.Now:HH:mm:ss.fff} frame={frame} - {path}");
        if (lines.Count == 0)
            return;
        _liveActors = live;
        File.AppendAllLines(Path.Combine(OutputDirectory, "timeline.log"), lines);
    }

    // What is actually attached to an actor root, and the full member list of every non-Unity
    // component on it. Live reflection, so no offline dump of the protected binary is involved.
    private const int ClassDumpDepth = 2;
    private const int ClassDumpLimit = 600;

    private static void DumpComponents(UnityApi api, List<IntPtr> actorRoots)
    {
        var summary = new List<string>();
        var newClasses = 0;

        foreach (var root in actorRoots)
        {
            var rootName = api.Name(root);
            if (!DumpedRoots.Add(rootName))
                continue;
            summary.Add(rootName);

            var values = new System.Text.StringBuilder();
            values.AppendLine($"# {rootName} @ {DateTime.Now:O}");
            var components = Il2.Invoke(api.GameObjectGetComponents, root, api.ComponentTypeObject);
            for (var index = 0; index < Il2.Length(components); index++)
            {
                var component = Il2.Item(components, index);
                if (component == IntPtr.Zero)
                    continue;
                var klass = Il2.il2cpp_object_get_class(component);
                var name = Il2.ClassName(klass);
                summary.Add($"   {name}");
                if (Il2.IsForeign(name))
                    continue;
                newClasses += DumpClassTree(klass, ClassDumpDepth);

                values.AppendLine();
                values.AppendLine($"== {name}");
                Il2.DumpInstance(component, 1, values, "   ", api.Name);
            }
            WriteDump("instance-dump", rootName, values.ToString());
        }

        if (summary.Count == 0)
            return;
        File.AppendAllLines(Path.Combine(OutputDirectory, "components.txt"), summary);
        Step($"components dumped: {newClasses} new classes ({DumpedClasses.Count} total)");
    }

    // Breadth-first over everything the actor's own classes mention, so one run yields the whole
    // Campus.*/VL.* type surface and later questions can be answered without launching the game.
    private static int DumpClassTree(IntPtr klass, int depth)
    {
        var written = 0;
        var frontier = new List<IntPtr> { klass };
        for (var level = 0; level <= depth && frontier.Count > 0; level++)
        {
            var next = new List<IntPtr>();
            foreach (var current in frontier)
            {
                if (current == IntPtr.Zero || DumpedClasses.Count >= ClassDumpLimit)
                    continue;
                var name = Il2.ClassName(current);
                if (Il2.IsForeign(name) || !DumpedClasses.Add(name))
                    continue;
                var referenced = new List<IntPtr>();
                var content = Il2.DumpClass(current, referenced);
                try { WriteDump("class-dump", name, content); written++; }
                catch (Exception exception) { Step($"class dump failed for {name}: {exception.Message}"); }
                if (level < depth)
                    next.AddRange(referenced);
            }
            frontier = next;
        }
        return written;
    }

    private static void WriteDump(string subdirectory, string name, string content)
    {
        var directory = Path.Combine(OutputDirectory, subdirectory);
        Directory.CreateDirectory(directory);
        var fileName = name;
        foreach (var invalid in Path.GetInvalidFileNameChars())
            fileName = fileName.Replace(invalid, '_');
        // Generic nested types produce names that blow past MAX_PATH; keep the readable head and
        // append a hash so distinct types never collide.
        if (fileName.Length > 100)
        {
            var hash = 2166136261u;
            foreach (var character in name)
                hash = (hash ^ character) * 16777619u;
            fileName = $"{fileName.Substring(0, 90)}~{hash:x8}";
        }
        File.WriteAllText(Path.Combine(directory, $"{fileName}.txt"), content);
    }

    private static AnimatorProbe ProbeAnimator(UnityApi api, IntPtr animator, IntPtr gameObject, int sceneHandle)
    {
        var transform = Il2.Invoke(api.ComponentGetTransform, animator);
        var avatar = Il2.Invoke(api.AnimatorGetAvatar, animator);
        var controller = Il2.Invoke(api.AnimatorController, animator);
        var isHuman = Il2.Bool(Il2.Invoke(api.AnimatorIsHuman, animator));

        var probe = new AnimatorProbe
        {
            path = api.Path(transform),
            sceneHandle = sceneHandle,
            enabled = Il2.Bool(Il2.Invoke(api.BehaviourGetEnabled, animator)),
            activeInHierarchy = Il2.Bool(Il2.Invoke(api.GameObjectGetActiveInHierarchy, gameObject)),
            isHuman = isHuman,
            isInitialized = Il2.Bool(Il2.Invoke(api.AnimatorIsInitialized, animator)),
            avatarName = api.Name(avatar),
            avatarValid = avatar != IntPtr.Zero && Il2.Bool(Il2.Invoke(api.AvatarIsValid, avatar)),
            avatarHuman = avatar != IntPtr.Zero && Il2.Bool(Il2.Invoke(api.AvatarIsHuman, avatar)),
            controllerName = api.Name(controller),
            applyRootMotion = Il2.Bool(Il2.Invoke(api.AnimatorApplyRootMotion, animator)),
            updateMode = Il2.Int(Il2.Invoke(api.AnimatorUpdateMode, animator)),
            cullingMode = Il2.Int(Il2.Invoke(api.AnimatorCullingMode, animator)),
        };

        if (isHuman)
        {
            // HumanBodyBones.Hips (0) .. LastBone (55, exclusive).
            var bones = new List<BoneProbe>(55);
            for (var bone = 0; bone < 55; bone++)
            {
                var boneTransform = Il2.Invoke(api.AnimatorGetBoneTransform, animator, Il2.Arg(bone));
                bones.Add(new BoneProbe
                {
                    bone = bone,
                    path = boneTransform == IntPtr.Zero ? string.Empty : api.Path(boneTransform),
                    local = boneTransform == IntPtr.Zero ? null : ProbeLocal(api, boneTransform),
                });
            }
            probe.bones = bones.ToArray();
        }

        var hierarchy = new List<HierarchyProbe>();
        WalkHierarchy(api, transform, api.Path(transform), hierarchy);
        probe.hierarchy = hierarchy.ToArray();

        var renderers = new List<RendererProbe>();
        // Renderer, not SkinnedMeshRenderer: Root_Face and props are not always skinned, and a
        // narrower query silently hid them.
        var found = Il2.Invoke(api.ComponentGetComponentsInChildren, animator, api.RendererTypeObject, Il2.Arg(true));
        for (var index = 0; index < Il2.Length(found); index++)
        {
            var renderer = Il2.Item(found, index);
            if (renderer != IntPtr.Zero)
                renderers.Add(ProbeRenderer(api, renderer));
        }
        probe.renderers = renderers.ToArray();
        return probe;
    }

    private static void WalkHierarchy(UnityApi api, IntPtr transform, string path, List<HierarchyProbe> sink)
    {
        sink.Add(new HierarchyProbe { path = path, local = ProbeLocal(api, transform) });
        var children = Il2.Int(Il2.Invoke(api.TransformGetChildCount, transform));
        for (var index = 0; index < children; index++)
        {
            var child = Il2.Invoke(api.TransformGetChild, transform, Il2.Arg(index));
            if (child == IntPtr.Zero)
                continue;
            WalkHierarchy(api, child, $"{path}/{api.Name(child)}", sink);
        }
    }

    private static LocalTransformProbe ProbeLocal(UnityApi api, IntPtr transform)
    {
        var position = Il2.Floats(Il2.Invoke(api.TransformLocalPosition, transform), 3);
        var rotation = Il2.Floats(Il2.Invoke(api.TransformLocalRotation, transform), 4);
        var scale = Il2.Floats(Il2.Invoke(api.TransformLocalScale, transform), 3);
        return new LocalTransformProbe
        {
            px = position[0], py = position[1], pz = position[2],
            rx = rotation[0], ry = rotation[1], rz = rotation[2], rw = rotation[3],
            sx = scale[0], sy = scale[1], sz = scale[2],
        };
    }

    private static RendererProbe ProbeRenderer(UnityApi api, IntPtr renderer)
    {
        // The skinned-only members must not be invoked on a plain MeshRenderer.
        var rendererType = Il2.ClassName(Il2.il2cpp_object_get_class(renderer));
        var skinned = rendererType == "UnityEngine.SkinnedMeshRenderer";
        var mesh = skinned ? Il2.Invoke(api.SkinnedSharedMesh, renderer) : IntPtr.Zero;
        var rootBone = skinned ? Il2.Invoke(api.SkinnedRootBone, renderer) : IntPtr.Zero;
        var boneArray = skinned ? Il2.Invoke(api.SkinnedBones, renderer) : IntPtr.Zero;
        var materialArray = Il2.Invoke(api.RendererSharedMaterials, renderer);

        var bones = new List<string>();
        for (var index = 0; index < Il2.Length(boneArray); index++)
        {
            var bone = Il2.Item(boneArray, index);
            bones.Add(bone == IntPtr.Zero ? string.Empty : api.Path(bone));
        }

        var materials = new List<MaterialProbe>();
        for (var index = 0; index < Il2.Length(materialArray); index++)
        {
            var material = Il2.Item(materialArray, index);
            materials.Add(new MaterialProbe
            {
                name = api.Name(material),
                shader = material == IntPtr.Zero ? string.Empty : api.Name(Il2.Invoke(api.MaterialGetShader, material)),
                // A mod body renders correctly in one scene and pitch black in another while keeping
                // the right shader and textures, so the difference is in these. The face part is
                // stock and renders fine in the same frame — it is the control.
                properties = ReadMaterialProperties(material),
            });
        }

        var blendShapes = new List<BlendShapeProbe>();
        if (mesh != IntPtr.Zero)
        {
            var shapeCount = Il2.Int(Il2.Invoke(api.MeshBlendShapeCount, mesh));
            for (var index = 0; index < shapeCount; index++)
            {
                blendShapes.Add(new BlendShapeProbe
                {
                    name = Il2.Str(Il2.Invoke(api.MeshGetBlendShapeName, mesh, Il2.Arg(index))),
                    weight = Il2.Float(Il2.Invoke(api.SkinnedBlendShapeWeight, renderer, Il2.Arg(index))),
                });
            }
        }

        return new RendererProbe
        {
            rendererType = rendererType,
            path = api.Path(Il2.Invoke(api.ComponentGetTransform, renderer)),
            enabled = Il2.Bool(Il2.Invoke(api.RendererGetEnabled, renderer)),
            meshName = api.Name(mesh),
            vertexCount = mesh == IntPtr.Zero ? 0 : Il2.Int(Il2.Invoke(api.MeshVertexCount, mesh)),
            subMeshCount = mesh == IntPtr.Zero ? 0 : Il2.Int(Il2.Invoke(api.MeshSubMeshCount, mesh)),
            rootBonePath = rootBone == IntPtr.Zero ? string.Empty : api.Path(rootBone),
            bones = bones.ToArray(),
            materials = materials.ToArray(),
            blendShapes = blendShapes.ToArray(),
        };
    }

    [Serializable] internal sealed class ProbeSnapshot
    {
        public string utc = string.Empty;
        public int frame;
        public int foundTotal;
        public int skippedNonScene;
        public AnimatorProbe[] animators = Array.Empty<AnimatorProbe>();
    }

    [Serializable] internal sealed class AnimatorProbe
    {
        public string path = string.Empty;
        public int sceneHandle;
        public bool enabled;
        public bool activeInHierarchy;
        public bool isHuman;
        public bool isInitialized;
        public string avatarName = string.Empty;
        public bool avatarValid;
        public bool avatarHuman;
        public string controllerName = string.Empty;
        public bool applyRootMotion;
        public int updateMode;
        public int cullingMode;
        public BoneProbe[] bones = Array.Empty<BoneProbe>();
        public HierarchyProbe[] hierarchy = Array.Empty<HierarchyProbe>();
        public RendererProbe[] renderers = Array.Empty<RendererProbe>();
    }

    [Serializable] internal sealed class BoneProbe
    {
        public int bone;
        public string path = string.Empty;
        public LocalTransformProbe? local;
    }

    [Serializable] internal sealed class HierarchyProbe
    {
        public string path = string.Empty;
        public LocalTransformProbe local = new();
    }

    [Serializable] internal sealed class LocalTransformProbe
    {
        public float px, py, pz;
        public float rx, ry, rz, rw;
        public float sx, sy, sz;
    }

    [Serializable] internal sealed class RendererProbe
    {
        public string rendererType = string.Empty;
        public string path = string.Empty;
        public bool enabled;
        public string meshName = string.Empty;
        public int vertexCount;
        public int subMeshCount;
        public string rootBonePath = string.Empty;
        public string[] bones = Array.Empty<string>();
        public MaterialProbe[] materials = Array.Empty<MaterialProbe>();
        public BlendShapeProbe[] blendShapes = Array.Empty<BlendShapeProbe>();
    }

    [Serializable] internal sealed class MaterialProbe
    {
        public string[] properties = Array.Empty<string>();
        public string name = string.Empty;
        public string shader = string.Empty;
    }

    [Serializable] internal sealed class BlendShapeProbe
    {
        public string name = string.Empty;
        public float weight;
    }
}

// Injected only to get a main-thread tick. Nothing here calls an interop proxy.
public sealed class ProbeBehaviour : MonoBehaviour
{
    private const int ScanIntervalFrames = 30;

    private int _frames;
    private bool _disabled;

    public ProbeBehaviour(IntPtr pointer) : base(pointer) { }

    public void Update()
    {
        if (_disabled || ++_frames % ScanIntervalFrames != 0)
            return;
        try
        {
            AvatarProbePlugin.Scan(_frames);
        }
        catch (Exception exception)
        {
            _disabled = true;
            AvatarProbePlugin.Step($"scan failed at frame {_frames}, ticking disabled: {exception}");
        }
    }
}
