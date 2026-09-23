// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonSyntaxException;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NamedNodeMap;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import verun.common.JsonValueConverter;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;

import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class JsonXml {
    private static final Gson GSON = new GsonBuilder().serializeNulls().create();
    private static final Gson PRETTY_GSON = new GsonBuilder().setPrettyPrinting().serializeNulls().create();
    private static final String XML_ATTRIBUTES_KEY = "@attributes";
    private static final String XML_TEXT_KEY = "#text";

    private JsonXml() {
    }

    public static Object parseJson(String json) {
        try {
            return JsonValueConverter.fromJson(json);
        } catch (JsonSyntaxException e) {
            throw new RuntimeException("Invalid JSON: " + e.getMessage());
        }
    }

    public static Object jsonToObj(String json) {
        return parseJson(json);
    }

    public static String toJson(Object value, boolean pretty) {
        return pretty ? PRETTY_GSON.toJson(value) : GSON.toJson(value);
    }

    public static String objToJson(Object value, boolean pretty) {
        return toJson(value, pretty);
    }

    public static Object readJson(String filePath) {
        return parseJson(readText(filePath));
    }

    public static String writeJson(String filePath, Object value, boolean pretty) {
        return writeText(filePath, toJson(value, pretty));
    }

    public static Map<String, Object> parseXml(String xml) {
        try {
            Document document = parseXmlDocument(xml);
            return elementToXmlObject(document.getDocumentElement());
        } catch (Exception e) {
            throw new RuntimeException("Invalid XML: " + e.getMessage());
        }
    }

    public static Map<String, Object> readXml(String filePath) {
        return parseXml(readText(filePath));
    }

    public static String writeXml(String filePath, String xml) {
        return writeText(filePath, xml);
    }

    public static String jsonToXml(Object value, String rootName) {
        String name = rootName == null || rootName.trim().isEmpty() ? "root" : rootName.trim();
        Object normalizedValue = normalizeJsonLikeValue(value);
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            DocumentBuilder builder = factory.newDocumentBuilder();
            Document doc = builder.newDocument();
            Element root = doc.createElement(name);
            doc.appendChild(root);
            appendValue(doc, root, normalizedValue);
            return documentToString(doc);
        } catch (ParserConfigurationException | TransformerException e) {
            throw new RuntimeException("Failed to create XML: " + e.getMessage());
        }
    }

    public static String xmlFromJson(Object value, String rootName) {
        return jsonToXml(value, rootName);
    }

    public static Object xmlToJson(String xml) {
        try {
            Document document = parseXmlDocument(xml);
            return elementToPlainValue(document.getDocumentElement());
        } catch (Exception e) {
            throw new RuntimeException("Invalid XML: " + e.getMessage());
        }
    }

    public static Object jsonFromXml(String xml) {
        return xmlToJson(xml);
    }

    public static Object xmlToObj(String xml) {
        return xmlToJson(xml);
    }

    public static String objToXml(Object value, String rootName) {
        if (value instanceof Map<?, ?> && isXmlWrapper((Map<?, ?>) value)) {
            @SuppressWarnings("unchecked")
            Map<String, Object> xmlObj = (Map<String, Object>) value;
            return xmlObjectToString(xmlObj);
        }
        return jsonToXml(value, rootName);
    }

    public static String readText(String filePath) {
        try {
            byte[] bytes = Files.readAllBytes(Path.of(filePath));
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new RuntimeException("Failed to read file: " + filePath + " (" + e.getMessage() + ")");
        }
    }

    public static String writeText(String filePath, String value) {
        try {
            Path path = Path.of(filePath);
            if (path.getParent() != null) {
                Files.createDirectories(path.getParent());
            }
            Files.writeString(path, value == null ? "" : value, StandardCharsets.UTF_8);
            return filePath;
        } catch (IOException e) {
            throw new RuntimeException("Failed to write file: " + filePath + " (" + e.getMessage() + ")");
        }
    }

    private static Document parseXmlDocument(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        Document document = builder.parse(new InputSource(new StringReader(xml)));
        document.getDocumentElement().normalize();
        return document;
    }

    private static Object normalizeJsonLikeValue(Object value) {
        if (!(value instanceof String)) {
            return value;
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            return "";
        }
        char first = text.charAt(0);
        if (first == '{' || first == '[') {
            return parseJson(text);
        }
        return value;
    }

    private static Map<String, Object> elementToXmlObject(Element element) {
        Map<String, Object> current = new LinkedHashMap<>();
        current.put("name", element.getTagName());

        Map<String, Object> attributes = new LinkedHashMap<>();
        NamedNodeMap attrMap = element.getAttributes();
        for (int i = 0; i < attrMap.getLength(); i++) {
            Node attr = attrMap.item(i);
            attributes.put(attr.getNodeName(), attr.getNodeValue());
        }
        current.put("attributes", attributes);

        List<Object> children = new ArrayList<>();
        StringBuilder text = new StringBuilder();
        NodeList childNodes = element.getChildNodes();
        for (int i = 0; i < childNodes.getLength(); i++) {
            Node child = childNodes.item(i);
            if (child.getNodeType() == Node.ELEMENT_NODE) {
                Map<String, Object> childWrapped = elementToXmlObject((Element) child);
                children.add(childWrapped);
                Object childRootObj = childWrapped.get("root");
                if (childRootObj instanceof Map<?, ?>) {
                    Map<?, ?> childRoot = (Map<?, ?>) childRootObj;
                    Object childNameObj = childRoot.get("name");
                    if (childNameObj != null) {
                        String childName = String.valueOf(childNameObj);
                        if ("name".equals(childName) || "attributes".equals(childName)
                                || "children".equals(childName) || "text".equals(childName)) {
                            continue;
                        }
                        Object existing = current.get(childName);
                        if (existing == null) {
                            current.put(childName, childWrapped);
                        } else if (existing instanceof List<?>) {
                            @SuppressWarnings("unchecked")
                            List<Object> existingList = (List<Object>) existing;
                            existingList.add(childWrapped);
                        } else {
                            List<Object> grouped = new ArrayList<>();
                            grouped.add(existing);
                            grouped.add(childWrapped);
                            current.put(childName, grouped);
                        }
                    }
                }
            } else if (child.getNodeType() == Node.TEXT_NODE) {
                String chunk = child.getTextContent();
                if (chunk != null && !chunk.trim().isEmpty()) {
                    if (text.length() > 0) {
                        text.append(" ");
                    }
                    text.append(chunk.trim());
                }
            }
        }

        current.put("children", children);
        current.put("text", text.length() > 0 ? text.toString() : "");

        Map<String, Object> wrapped = new LinkedHashMap<>();
        wrapped.put("root", current);
        wrapped.put("name", current.get("name"));
        wrapped.put("attributes", current.get("attributes"));
        wrapped.put("children", current.get("children"));
        wrapped.put("text", current.get("text"));
        for (Map.Entry<String, Object> entry : current.entrySet()) {
            String key = entry.getKey();
            if ("name".equals(key) || "attributes".equals(key) || "children".equals(key) || "text".equals(key)) {
                continue;
            }
            wrapped.put(key, entry.getValue());
        }
        return wrapped;
    }

    private static Object elementToPlainValue(Element element) {
        List<Element> childElements = childElements(element);
        String text = collectText(element);
        Map<String, Object> attributes = collectAttributes(element);

        if (childElements.isEmpty()) {
            if (attributes.isEmpty()) {
                return JsonValueConverter.coerceStringScalar(text);
            }
            Map<String, Object> out = new LinkedHashMap<>();
            out.put(XML_ATTRIBUTES_KEY, attributes);
            if (!text.isEmpty()) {
                out.put(XML_TEXT_KEY, JsonValueConverter.coerceStringScalar(text));
            }
            return out;
        }

        if (attributes.isEmpty() && text.isEmpty() && allChildrenNamed(childElements, "item")) {
            List<Object> list = new ArrayList<>();
            for (Element child : childElements) {
                list.add(elementToPlainValue(child));
            }
            return list;
        }

        Map<String, Object> out = new LinkedHashMap<>();
        if (!attributes.isEmpty()) {
            out.put(XML_ATTRIBUTES_KEY, attributes);
        }
        if (!text.isEmpty()) {
            out.put(XML_TEXT_KEY, JsonValueConverter.coerceStringScalar(text));
        }
        for (Element child : childElements) {
            mergeChildValue(out, child.getTagName(), elementToPlainValue(child));
        }
        return out;
    }

    private static List<Element> childElements(Element element) {
        List<Element> children = new ArrayList<>();
        NodeList childNodes = element.getChildNodes();
        for (int i = 0; i < childNodes.getLength(); i++) {
            Node child = childNodes.item(i);
            if (child.getNodeType() == Node.ELEMENT_NODE) {
                children.add((Element) child);
            }
        }
        return children;
    }

    private static Map<String, Object> collectAttributes(Element element) {
        Map<String, Object> attributes = new LinkedHashMap<>();
        NamedNodeMap attrMap = element.getAttributes();
        for (int i = 0; i < attrMap.getLength(); i++) {
            Node attr = attrMap.item(i);
            attributes.put(attr.getNodeName(), attr.getNodeValue());
        }
        return attributes;
    }

    private static String collectText(Element element) {
        StringBuilder text = new StringBuilder();
        NodeList childNodes = element.getChildNodes();
        for (int i = 0; i < childNodes.getLength(); i++) {
            Node child = childNodes.item(i);
            if (child.getNodeType() == Node.TEXT_NODE) {
                String chunk = child.getTextContent();
                if (chunk != null && !chunk.trim().isEmpty()) {
                    if (text.length() > 0) {
                        text.append(' ');
                    }
                    text.append(chunk.trim());
                }
            }
        }
        return text.toString();
    }

    private static boolean allChildrenNamed(List<Element> children, String name) {
        if (children.isEmpty()) {
            return false;
        }
        for (Element child : children) {
            if (!name.equals(child.getTagName())) {
                return false;
            }
        }
        return true;
    }

    private static void mergeChildValue(Map<String, Object> target, String key, Object value) {
        Object existing = target.get(key);
        if (existing == null) {
            target.put(key, value);
            return;
        }
        if (existing instanceof List<?>) {
            @SuppressWarnings("unchecked")
            List<Object> list = (List<Object>) existing;
            list.add(value);
            return;
        }
        List<Object> grouped = new ArrayList<>();
        grouped.add(existing);
        grouped.add(value);
        target.put(key, grouped);
    }

    private static void appendValue(Document doc, Element parent, Object value) {
        if (value == null) {
            return;
        }
        if (value instanceof Map<?, ?>) {
            appendMapValue(doc, parent, (Map<?, ?>) value);
            return;
        }
        if (value instanceof List<?>) {
            for (Object item : (List<?>) value) {
                Element itemEl = doc.createElement("item");
                parent.appendChild(itemEl);
                appendValue(doc, itemEl, item);
            }
            return;
        }
        parent.appendChild(doc.createTextNode(String.valueOf(value)));
    }

    private static void appendMapValue(Document doc, Element parent, Map<?, ?> map) {
        Object attrsObj = map.get(XML_ATTRIBUTES_KEY);
        if (attrsObj instanceof Map<?, ?>) {
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) attrsObj).entrySet()) {
                if (entry.getKey() == null) {
                    continue;
                }
                parent.setAttribute(String.valueOf(entry.getKey()), String.valueOf(entry.getValue()));
            }
        }

        Object textObj = map.get(XML_TEXT_KEY);
        if (textObj != null) {
            parent.appendChild(doc.createTextNode(String.valueOf(textObj)));
        }

        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (entry.getKey() == null) {
                continue;
            }
            String key = String.valueOf(entry.getKey());
            if (XML_ATTRIBUTES_KEY.equals(key) || XML_TEXT_KEY.equals(key)) {
                continue;
            }
            Element child = doc.createElement(key);
            parent.appendChild(child);
            appendValue(doc, child, entry.getValue());
        }
    }

    private static String documentToString(Document doc) throws TransformerException {
        TransformerFactory tf = TransformerFactory.newInstance();
        Transformer transformer = tf.newTransformer();
        transformer.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes");
        transformer.setOutputProperty(OutputKeys.INDENT, "yes");
        transformer.setOutputProperty("{http://xml.apache.org/xslt}indent-amount", "2");
        StringWriter writer = new StringWriter();
        transformer.transform(new DOMSource(doc), new StreamResult(writer));
        return writer.toString();
    }

    private static boolean isXmlWrapper(Map<?, ?> map) {
        Object root = map.get("root");
        if (!(root instanceof Map<?, ?>)) {
            return false;
        }
        Map<?, ?> rootMap = (Map<?, ?>) root;
        return rootMap.containsKey("name")
                && rootMap.containsKey("attributes")
                && rootMap.containsKey("children")
                && rootMap.containsKey("text");
    }

    private static String xmlObjectToString(Map<String, Object> xmlObj) {
        try {
            Object rootObj = xmlObj.get("root");
            if (!(rootObj instanceof Map<?, ?>)) {
                throw new RuntimeException("Invalid XML object: missing root");
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> rootMap = (Map<String, Object>) rootObj;

            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            DocumentBuilder builder = factory.newDocumentBuilder();
            Document doc = builder.newDocument();
            Element root = elementFromMap(doc, rootMap);
            doc.appendChild(root);
            return documentToString(doc);
        } catch (ParserConfigurationException | TransformerException e) {
            throw new RuntimeException("Failed to convert XML object to XML: " + e.getMessage());
        }
    }

    private static Element elementFromMap(Document doc, Map<String, Object> nodeMap) {
        String name = String.valueOf(nodeMap.getOrDefault("name", "root"));
        Element element = doc.createElement(name);

        Object attrsObj = nodeMap.get("attributes");
        if (attrsObj instanceof Map<?, ?>) {
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) attrsObj).entrySet()) {
                if (entry.getKey() == null) {
                    continue;
                }
                element.setAttribute(String.valueOf(entry.getKey()), String.valueOf(entry.getValue()));
            }
        }

        Object childrenObj = nodeMap.get("children");
        if (childrenObj instanceof List<?>) {
            for (Object child : (List<?>) childrenObj) {
                if (!(child instanceof Map<?, ?>)) {
                    continue;
                }
                Map<?, ?> childMap = (Map<?, ?>) child;
                Object childRoot = childMap.get("root");
                if (childRoot instanceof Map<?, ?>) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> childRootMap = (Map<String, Object>) childRoot;
                    element.appendChild(elementFromMap(doc, childRootMap));
                }
            }
        }

        Object textObj = nodeMap.get("text");
        String text = textObj == null ? "" : String.valueOf(textObj);
        if (!text.isEmpty() && (childrenObj == null || !(childrenObj instanceof List<?>) || ((List<?>) childrenObj).isEmpty())) {
            element.appendChild(doc.createTextNode(text));
        }

        return element;
    }
}
